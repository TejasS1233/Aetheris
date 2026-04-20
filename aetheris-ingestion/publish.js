import mqtt from 'mqtt'
import { createReadStream } from 'fs'
import csv from 'csv-parser'

const MQTT_BROKER = 'mqtt://localhost:1883'
const DATA_FILE = '../data/transactions.csv'
const PUBLISH_DELAY_MS = 1

const client = mqtt.connect(MQTT_BROKER)

client.on('connect', async () => {
  console.log('Connected to EMQX broker')

  const results = []
  createReadStream(DATA_FILE)
    .pipe(csv())
    .on('data', (data) => results.push(data))
    .on('end', async () => {
      console.log(`Read ${results.length} transactions, publishing...`)

      for (const data of results) {
        const topic = `aetheris/transactions/${data.AccountOriginID}/${data.TransactionID}`
        const payload = JSON.stringify({
          transactionId: parseInt(data.TransactionID),
          accountOrigin: data.AccountOriginID,
          accountDestination: data.AccountDestinationID,
          amount: parseFloat(data.Amount),
          type: parseInt(data.TransactionTypeID),
          branch: parseInt(data.BranchID),
          date: data.TransactionDate,
          description: data.Description
        })

        client.publish(topic, payload)
        await new Promise(resolve => setTimeout(resolve, PUBLISH_DELAY_MS))
      }

      console.log(`Published ${results.length} transactions`)
      setTimeout(() => client.end(), 1000)
    })
})

client.on('error', (err) => {
  console.error('Connection error:', err.message)
})
