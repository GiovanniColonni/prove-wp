import express from 'express'
import morgan from 'morgan'
import cors from 'cors'
import dotenv from 'dotenv'
import { createExplicitApiRouter } from './ws-api/endpoints.js'

dotenv.config()

const app = express()

app.use(cors())
app.use(express.json({ limit: '1mb' }))
app.use(morgan('dev'))

app.get('/health', (req, res) => {
  res.status(200).json({ status: 'ok' })
})

// Mount explicit API routes
app.use(createExplicitApiRouter())

const port = Number(process.env.PORT || 3000)
const host = process.env.HOST || '0.0.0.0'

app.listen(port, host, () => {
  // eslint-disable-next-line no-console
  console.log(`whisper-power-api listening on http://${host}:${port}`)
})



