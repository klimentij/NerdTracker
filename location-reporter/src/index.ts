import { createClient } from '@supabase/supabase-js'

// Configurable parameters
const TABLE_NAME = 'locations'
const EMAIL_SUBJECT = 'Locations submitted'
const EMAIL_CONTENT = (count: number) => `Locations submitted: ${count}`

interface Env {
  SUPABASE_URL: string
  SUPABASE_KEY: string
  TELEGRAM_BOT_TOKEN: string
  TELEGRAM_CHAT_ID: string
}

export default {
  // No public fetch endpoint
  async fetch(_request: Request): Promise<Response> {
    return new Response('This worker only handles scheduled events.', { status: 200 })
  },

  // Cron trigger fires every 3 minutes
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    console.log(`[location-reporter] Starting scheduled run at ${new Date().toISOString()}`)
    // Initialize Supabase client
    const supabase = createClient(env.SUPABASE_URL, env.SUPABASE_KEY)

    // Query the most recent row by id, then check tst in code
    const { data: latestRows, error: latestError } = await supabase
      .from(TABLE_NAME)
      .select('*') // Changed from 'tst' to '*' like inserter
      .not('tst', 'is', null) // Filter out rows where tst is NULL
      .order('tst', { ascending: false }) // Changed from 'id' to 'tst' like inserter
      .limit(1)

    // **DEBUG LOGGING**
    console.log('[location-reporter] Supabase query results (no DB null filter):')
    console.log(`  - Error: ${JSON.stringify(latestError)}`)
    console.log(`  - Data: ${JSON.stringify(latestRows)}`)
    if (latestRows && latestRows.length > 0) {
      console.log(`  - First row: ${JSON.stringify(latestRows[0])}`)
      console.log(`  - First row tst value: ${latestRows[0]?.tst}`)
      console.log(`  - First row tst type: ${typeof latestRows[0]?.tst}`)
    }
    // **END DEBUG LOGGING**

    if (latestError) {
      console.error('[location-reporter] Error fetching latest timestamp:', latestError)
      return
    }

    // Check if we have a valid, recent location
    if (latestRows && latestRows.length > 0 && latestRows[0]?.tst && latestRows[0]?.lat && latestRows[0]?.lon) {
      const lastTst = latestRows[0].tst
      const nowEpoch = Math.floor(Date.now() / 1000)
      const secondsAgo = nowEpoch - lastTst

      console.log(`[location-reporter] Last valid location was ${secondsAgo} seconds ago (epoch: ${lastTst}).`) // Log the age regardless

      // Only notify if older than 10 minutes (600 seconds)
      if (secondsAgo > 600) {
        let humanAgo = ''
        if (secondsAgo < 3600) {
          humanAgo = `${Math.floor(secondsAgo / 60)} minutes ${secondsAgo % 60} seconds ago`
        } else if (secondsAgo < 86400) {
          humanAgo = `${Math.floor(secondsAgo / 3600)} hours ${Math.floor((secondsAgo % 3600) / 60)} minutes ago`
        } else {
          const days = Math.floor(secondsAgo / 86400)
          const hours = Math.floor((secondsAgo % 86400) / 3600)
          humanAgo = `${days} days ${hours} hours ago`
        }

        // Helper function to escape MarkdownV2 characters
        const escapeMdV2 = (str: string | number | null | undefined): string => {
          if (str === null || str === undefined) return '';
          // Escape characters: _ * [ ] ( ) ~ ` > # + - = | { } . !
          return String(str).replace(/([_*[\]()~`>#+\-=|{}.!])/g, '\\$1');
        };

        // Extract details from the latest row
        const lastRecord = latestRows[0]
        const lat = lastRecord.lat
        const lon = lastRecord.lon
        const googleMapsLink = `https://www.google.com/maps?q=${lat},${lon}` // URL should NOT be escaped

        // Build the details string, escaping values
        let details = ''
        if (lastRecord.acc !== null) details += `🎯 Accuracy: ${escapeMdV2(lastRecord.acc)}m\n`
        if (lastRecord.vel !== null) details += `💨 Speed: ${escapeMdV2(lastRecord.vel)} km/h\n` // Assuming km/h
        if (lastRecord.alt !== null) details += `⛰️ Altitude: ${escapeMdV2(lastRecord.alt)}m\n`
        if (lastRecord.batt !== null) details += `🔋 Battery: ${escapeMdV2(lastRecord.batt)}%\n`
        const connType = lastRecord.conn === 'w' ? 'WiFi' : lastRecord.conn === 'm' ? 'Mobile' : lastRecord.conn === 'o' ? 'Offline' : 'Unknown';
        if (lastRecord.conn !== null) details += `📶 Connection: ${escapeMdV2(connType)}\n`
        if (lastRecord.conn === 'w' && lastRecord.ssid) details += `📡 WiFi SSID: ${escapeMdV2(lastRecord.ssid)}\n`

        // Escape the human-readable time ago string
        const humanAgoEscaped = escapeMdV2(humanAgo);
        
        // Construct the final MarkdownV2 message
        const lastTimestampMsg = 
`⚠️ *NerdTracker Alert* ⚠️

Last valid location recorded: *${humanAgoEscaped}*
\\(Epoch: ${escapeMdV2(lastTst)}\\)

📍 [View on Google Maps](${googleMapsLink})

*Details:*
${details}` // details already escaped

        console.log(`[location-reporter] Alert Message Payload:\n${lastTimestampMsg}`) // Log the formatted message

        // Send message via Telegram Bot API
        const messageText = lastTimestampMsg
        const telegramUrl = `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`
        console.log(`[location-reporter] Sending Telegram message to chat_id=${env.TELEGRAM_CHAT_ID}`)
        const sendResp = await fetch(telegramUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            chat_id: env.TELEGRAM_CHAT_ID,
            text: messageText,
            parse_mode: 'MarkdownV2', // Use MarkdownV2 for better formatting
            disable_web_page_preview: true // Optional: disable link preview
          }),
        })
        if (!sendResp.ok) {
          const respText = await sendResp.text()
          console.error(`[location-reporter] Error sending Telegram message: ${sendResp.status} ${respText}`)
        } else {
          console.log(`[location-reporter] Telegram alert message sent successfully: ${lastTimestampMsg}`)
        }
      } else {
        console.log('[location-reporter] Last location is recent (within 10 minutes). No alert needed.')
      }
    } else {
      // Handle case where no valid rows are found (or initial state)
      const noLocationMsg = 'No valid locations recorded yet or latest lacks coordinates.'
      console.log(`[location-reporter] ${noLocationMsg}`)
      // Optionally send a different Telegram message here if desired, e.g., initial setup confirmation
      // For now, we won't send anything in this case.
    }
  },
} satisfies ExportedHandler<Env>
