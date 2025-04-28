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

    let lastTimestampMsg = 'No locations recorded yet.'
    if (latestRows && latestRows.length > 0 && latestRows[0]?.tst) { // Check explicitly for existence/truthiness
      const lastTst = latestRows[0].tst
      const nowEpoch = Math.floor(Date.now() / 1000)
      const secondsAgo = nowEpoch - lastTst
      let humanAgo = ''
      if (secondsAgo < 60) {
        humanAgo = `${secondsAgo} seconds ago`
      } else if (secondsAgo < 3600) {
        humanAgo = `${Math.floor(secondsAgo/60)} minutes ${secondsAgo%60} seconds ago`
      } else if (secondsAgo < 86400) {
        humanAgo = `${Math.floor(secondsAgo/3600)} hours ${Math.floor((secondsAgo%3600)/60)} minutes ago`
      } else {
        const days = Math.floor(secondsAgo/86400)
        const hours = Math.floor((secondsAgo%86400)/3600)
        humanAgo = `${days} days ${hours} hours ago`
      }
      lastTimestampMsg = `Last location recorded: ${humanAgo} (epoch: ${lastTst})`
    }
    console.log(`[location-reporter] ${lastTimestampMsg}`)

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
        parse_mode: 'HTML'
      }),
    })
    if (!sendResp.ok) {
      const respText = await sendResp.text()
      console.error(`[location-reporter] Error sending Telegram message: ${sendResp.status} ${respText}`)
    } else {
      console.log(`[location-reporter] Telegram message sent successfully: ${lastTimestampMsg}`)
    }
  },
} satisfies ExportedHandler<Env>
