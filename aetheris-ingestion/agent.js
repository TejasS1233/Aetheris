import 'dotenv/config'
import mqtt from 'mqtt'
import Groq from 'groq'

const MQTT_BROKER = 'mqtt://localhost:1883'
const EXCEPTION_TOPIC = 'aetheris/exceptions'
const COMMAND_TOPIC = 'aetheris/commands'

const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY || 'your_groq_api_key_here'
})

const client = mqtt.connect(MQTT_BROKER)

const agents = {
  analyst: {
    name: 'Analyst',
    role: 'You are a financial forensics analyst. Analyze transaction anomalies and determine if they indicate fraud, error, or legitimate high-value transaction.'
  },
  auditor: {
    name: 'Auditor',
    role: 'You are a compliance auditor. Check if the transaction follows all regulatory requirements and flag any compliance concerns.'
  },
  strategist: {
    name: 'Strategist',
    role: 'You are a risk strategist. Assess the business risk of the transaction and recommend appropriate action.'
  }
}

function getAction(agentKey, exception) {
  const agent = agents[agentKey]
  return `You are ${agent.name}. ${agent.role}

Analyze this exception:
- Account: ${exception.accountOrigin}
- Amount: $${exception.amount}
- Transaction type: ${exception.type}
- Branch: ${exception.branch}
- Z-Score: ${exception.zScore} (how unusual)

Respond with ONLY ONE word: APPROVE, REVIEW, or BLOCK`
}

async function runAgent(agentKey, exception) {
  try {
    const completion = await groq.chat.completions.create({
      messages: [
        { role: 'user', content: getAction(agentKey, exception) }
      ],
      model: 'llama-3.1-70b-versatile',
      temperature: 0.1,
      max_tokens: 50
    })
    
    const response = completion.choices[0]?.message?.content?.trim().toUpperCase()
    return response || 'REVIEW'
  } catch (err) {
    console.error(`[${agentKey}] Error:`, err.message)
    return 'REVIEW'
  }
}

async function processException(exception) {
  console.log(`[AgentSystem] Processing exception: Account ${exception.accountOrigin} | $${exception.amount}`)
  
  const results = await Promise.all([
    runAgent('analyst', exception),
    runAgent('auditor', exception),
    runAgent('strategist', exception)
  ])
  
  console.log(`[AgentSystem] Votes: Analyst=${results[0]}, Auditor=${results[1]}, Strategist=${results[2]}`)
  
  const votes = results.filter(v => v === 'APPROVE').length
  let action = 'REVIEW'
  
  if (votes >= 2) action = 'APPROVE'
  else if (results.filter(v => v === 'BLOCK').length >= 2) action = 'BLOCK'
  
  const command = {
    ...exception,
    action,
    agentsVote: {
      analyst: results[0],
      auditor: results[1],
      strategist: results[2]
    },
    consensus: action,
    timestamp: Date.now()
  }
  
  client.publish(COMMAND_TOPIC, JSON.stringify(command))
  console.log(`[AgentSystem] COMMAND: ${action}`)
}

client.on('connect', () => {
  console.log('[AgentSystem] Connected to EMQX broker')
  console.log('[AgentSystem] Subscribed to:', EXCEPTION_TOPIC)
  
  client.subscribe(EXCEPTION_TOPIC, (err) => {
    if (err) console.error('Subscription error:', err.message)
  })
})

let exceptionCount = 0

client.on('message', (topic, message) => {
  exceptionCount++
  const exception = JSON.parse(message.toString())
  processException(exception)
})

client.on('error', (err) => {
  console.error('Connection error:', err.message)
})