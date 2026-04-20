import 'dotenv/config'
import mqtt from 'mqtt'
import Groq from 'groq'

const MQTT_BROKER = 'mqtt://localhost:1883'
const EXCEPTION_TOPIC = 'aetheris/exceptions'
const COMMAND_TOPIC = 'aetheris/commands'
const AGENT_COMM_TOPIC = 'aetheris/agents/'

const groq = new Groq({
  apiKey: process.env.GROQ_API_KEY || 'your_groq_api_key_here'
})

const client = mqtt.connect(MQTT_BROKER)

class Agent {
  constructor(name, role, tools = []) {
    this.name = name
    this.role = role
    this.tools = tools
    this.memory = []
    this.inbox = []
    this.outbox = []
  }

  addToMemory(message) {
    this.memory.push(message)
    if (this.memory.length > 10) this.memory.shift()
  }

  async think(context) {
    const systemPrompt = `You are ${this.name}, ${this.role}

You have access to these tools:
${this.tools.map(t => `- ${t.name}: ${t.description}`).join('\n')}

Your memory:
${this.memory.map(m => `${m.from}: ${m.content}`).join('\n')}

Current situation:
${context}

Think step by step. Make a decision. Use a tool if needed.
Respond with your final decision in this format:
DECISION: [APPROVE|BLOCK|REVIEW]
REASON: [your reasoning]`

    try {
      const completion = await groq.chat.completions.create({
        messages: [{ role: 'user', content: systemPrompt }],
        model: 'llama-3.1-70b-versatile',
        temperature: 0.2,
        max_tokens: 200
      })
      
      const response = completion.choices[0]?.message?.content || ''
      
      const decisionMatch = response.match(/DECISION:\s*(\w+)/i)
      const reasonMatch = response.match(/REASON:\s*(.+)/i)
      
      const decision = decisionMatch ? decisionMatch[1].toUpperCase() : 'REVIEW'
      const reason = reasonMatch ? reasonMatch[1].trim() : response.substring(0, 100)
      
      return { decision, reason, raw: response }
    } catch (err) {
      console.error(`[${this.name}] Error:`, err.message)
      return { decision: 'REVIEW', reason: 'Agent error', raw: '' }
    }
  }

  sendMessage(to, content) {
    const msg = { from: this.name, to, content, timestamp: Date.now() }
    this.outbox.push(msg)
    return msg
  }
}

class MultiAgentSystem {
  constructor() {
    this.agents = {}
    this.pendingConsensus = new Map()
    this.setupAgents()
  }

  setupAgents() {
    this.agents.analyst = new Agent(
      'Analyst',
      'Financial forensics expert. Your job is to detect fraud patterns.',
      [
        { name: 'query_history', description: 'Query transaction history for an account' },
        { name: 'calculate_risk', description: 'Calculate risk score based on patterns' }
      ]
    )

    this.agents.auditor = new Agent(
      'Auditor',
      'Compliance officer. Your job is to ensure regulatory compliance.',
      [
        { name: 'check_rules', description: 'Check if transaction violates any rules' },
        { name: 'verify_identity', description: 'Verify customer identity and credentials' }
      ]
    )

    this.agents.strategist = new Agent(
      'Strategist',
      'Risk strategist. Your job is to balance risk vs business opportunity.',
      [
        { name: 'assess_business_impact', description: 'Assess business impact of decision' },
        { name: 'calculate_loss', description: 'Calculate potential loss if transaction is fraudulent' }
      ]
    )

    console.log('[MAS] Agents initialized:', Object.keys(this.agents).join(', '))
  }

  async process(exception) {
    const taskId = `task_${Date.now()}`
    console.log(`[MAS] Starting consensus for: Account ${exception.accountOrigin} | $${exception.amount}`)

    const context = `
EXCEPTION DETECTED:
- Account: ${exception.accountOrigin}
- Amount: $${exception.amount}  
- Transaction Type: ${exception.type}
- Branch: ${exception.branch}
- Z-Score: ${exception.zScore} (${Math.abs(exception.zScore) > 3 ? 'highly unusual' : 'somewhat unusual'})
- Detected by: ${exception.detectedBy}
`

    const results = await Promise.all([
      this.agents.analyst.think(context),
      this.agents.auditor.think(context),
      this.agents.strategist.think(context)
    ])

    console.log(`[MAS] Analyst: ${results[0].decision}, Auditor: ${results[1].decision}, Strategist: ${results[2].decision}`)

    const approveCount = results.filter(r => r.decision === 'APPROVE').length
    const blockCount = results.filter(r => r.decision === 'BLOCK').length

    let consensus = 'REVIEW'
    if (approveCount >= 2) consensus = 'APPROVE'
    else if (blockCount >= 2) consensus = 'BLOCK'

    console.log(`[MAS] Consensus reached: ${consensus}`)

    const command = {
      ...exception,
      action: consensus,
      agents: {
        analyst: { decision: results[0].decision, reason: results[0].reason },
        auditor: { decision: results[1].decision, reason: results[1].reason },
        strategist: { decision: results[2].decision, reason: results[2].reason }
      },
      timestamp: Date.now()
    }

    return command
  }
}

const mas = new MultiAgentSystem()

client.on('connect', () => {
  console.log('[AgentSystem] Connected to EMQX')
  console.log('[AgentSystem] Subscribed to:', EXCEPTION_TOPIC)
  
  client.subscribe(EXCEPTION_TOPIC, (err) => {
    if (err) console.error('Subscription error:', err.message)
  })
})

client.on('message', async (topic, message) => {
  const exception = JSON.parse(message.toString())
  console.log(`[AgentSystem] Received exception: ${exception.accountOrigin} $${exception.amount}`)
  
  const command = await mas.process(exception)
  
  client.publish(COMMAND_TOPIC, JSON.stringify(command))
  console.log(`[AgentSystem] Published command: ${command.action}`)
})

client.on('error', (err) => {
  console.error('Connection error:', err.message)
})