import mqtt from 'mqtt'

const args = process.argv.slice(2)
const nodeName = args.find(a => a.startsWith('--node-name='))?.split('=')[1] || 'EdgeNode'
const nodeCount = Number(args.find(a => a.startsWith('--node-count='))?.split('=')[1]) || 5

const MQTT_BROKER = 'mqtt://localhost:1883'
const EXCEPTION_TOPIC = 'aetheris/exceptions'
const Z_THRESHOLD = 2.5

const TOPIC = 'aetheris/transactions/+/+'

function getNodeForAccount(accountId) {
  const idNum = parseInt(accountId)
  const nodeIndex = idNum % nodeCount
  return `EdgeNode${nodeIndex + 1}`
}

console.log(`Testing distribution: 200000->${getNodeForAccount(200000)}, 200001->${getNodeForAccount(200001)}, 201000->${getNodeForAccount(201000)}`)

function shouldProcess(accountId) {
  return getNodeForAccount(accountId) === nodeName
}

const accountWindows = {}
let exceptionCount = 0
let totalProcessed = 0

const client = mqtt.connect(MQTT_BROKER)

function calculateZScore(amount, history) {
  if (history.length < 5) return 0

  const mean = history.reduce((a, b) => a + b, 0) / history.length
  const variance = history.reduce((sum, val) => sum + (val - mean) ** 2, 0) / history.length
  const std = Math.sqrt(variance)

  if (std === 0) return 0
  return (amount - mean) / std
}

client.on('connect', () => {
  console.log(`[${nodeName}] Connected to EMQX broker`)
  console.log(`[${nodeName}] Topic: ${TOPIC}`)
  console.log(`[${nodeName}] Nodes: ${nodeCount} (hashing), Z-threshold: ${Z_THRESHOLD}`)

  client.subscribe(TOPIC, (err) => {
    if (err) console.error('Subscription error:', err.message)
  })
})

let messageCount = 0
let lastPrint = Date.now()

client.on('message', (topic, message) => {
  const data = JSON.parse(message.toString())
  const accountId = data.accountOrigin
  const amount = data.amount

  if (!shouldProcess(accountId)) return

  if (!accountWindows[accountId]) {
    accountWindows[accountId] = []
  }

  const history = accountWindows[accountId]
  const zScore = calculateZScore(amount, history)

  history.push(amount)
  if (history.length > 100) history.shift()

  if (Math.abs(zScore) > Z_THRESHOLD) {
    exceptionCount++
    const exception = {
      ...data,
      zScore: zScore.toFixed(2),
      timestamp: Date.now(),
      accountHistoryLength: history.length
    }
    client.publish(EXCEPTION_TOPIC, JSON.stringify({
      ...exception,
      detectedBy: nodeName
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