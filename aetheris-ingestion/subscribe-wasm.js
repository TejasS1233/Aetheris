import mqtt from 'mqtt'
import { readFile } from 'fs/promises'

const args = process.argv.slice(2)
const nodeName = args.find(a => a.startsWith('--node-name='))?.split('=')[1] || 'EdgeNode1'
const nodeCount = Number(args.find(a => a.startsWith('--node-count='))?.split('=')[1]) || 5
const wasmPath = args.find(a => a.startsWith('--wasm-path='))?.split('=')[1]
  || '../aetheris-edge-wasm/target/wasm32-unknown-unknown/release/aetheris_edge_wasm.wasm'

const MQTT_BROKER = 'mqtt://localhost:1883'
const EXCEPTION_TOPIC = 'aetheris/exceptions'
const TOPIC = 'aetheris/transactions/+/+'
const Z_THRESHOLD = 2.5
const WINDOW_SIZE = 100

function getNodeForAccount(accountId) {
  const idNum = parseInt(accountId, 10)
  const nodeIndex = idNum % nodeCount
  return `EdgeNode${nodeIndex + 1}`
}

function shouldProcess(accountId) {
  return getNodeForAccount(accountId) === nodeName
}

async function loadWasmExports() {
  const bytes = await readFile(wasmPath)
  const { instance } = await WebAssembly.instantiate(bytes)
  if (!instance.exports.z_score_from_stats) {
    throw new Error('Wasm function z_score_from_stats not found')
  }
  return instance.exports
}

function makeWindowState() {
  return {
    values: [],
    sum: 0,
    sumSq: 0
  }
}

function pushAmount(state, amount) {
  state.values.push(amount)
  state.sum += amount
  state.sumSq += amount * amount

  if (state.values.length > WINDOW_SIZE) {
    const removed = state.values.shift()
    state.sum -= removed
    state.sumSq -= removed * removed
  }
}

async function main() {
  const wasm = await loadWasmExports()
  const zScoreFromStats = wasm.z_score_from_stats

  const accountWindows = {}
  let exceptionCount = 0
  let totalProcessed = 0
  let messageCount = 0
  let lastPrint = Date.now()

  const client = mqtt.connect(MQTT_BROKER)

  client.on('connect', () => {
    console.log(`[${nodeName}] Connected to EMQX broker (Rust+Wasm scoring)`)
    console.log(`[${nodeName}] Topic: ${TOPIC}`)
    console.log(`[${nodeName}] Nodes: ${nodeCount} (hashing), Z-threshold: ${Z_THRESHOLD}`)
    console.log(`[${nodeName}] Wasm module: ${wasmPath}`)

    client.subscribe(TOPIC, (err) => {
      if (err) console.error('Subscription error:', err.message)
    })
  })

  client.on('message', (topic, message) => {
    const data = JSON.parse(message.toString())
    const accountId = data.accountOrigin
    const amount = data.amount

    if (!shouldProcess(accountId)) return

    if (!accountWindows[accountId]) {
      accountWindows[accountId] = makeWindowState()
    }

    const state = accountWindows[accountId]
    const zScore = Number(zScoreFromStats(state.sum, state.sumSq, state.values.length, amount))

    pushAmount(state, amount)

    if (Math.abs(zScore) > Z_THRESHOLD) {
      exceptionCount++
      client.publish(EXCEPTION_TOPIC, JSON.stringify({
        ...data,
        zScore: zScore.toFixed(2),
        timestamp: Date.now(),
        accountHistoryLength: state.values.length,
        detectedBy: `${nodeName}-wasm`
      }))
      console.log(`[${nodeName}] EXCEPTION: Account ${accountId} | $${amount} | z=${zScore.toFixed(2)}`)
    }

    totalProcessed++
    messageCount++
    const now = Date.now()
    if (now - lastPrint >= 1000) {
      console.log(`[${nodeName}] ${messageCount} msgs/sec | ${exceptionCount} exceptions | ${totalProcessed} total`)
      messageCount = 0
      lastPrint = now
    }
  })

  client.on('error', (err) => {
    console.error('Connection error:', err.message)
  })
}

main().catch((err) => {
  console.error('Failed to start Wasm edge node:', err.message)
  process.exit(1)
})
