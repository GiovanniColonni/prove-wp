import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import axios from 'axios'
import express from 'express'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const CSV_RELATIVE = '../../har_output/url_to_responses.csv'

function parseCsvLine(line) {
  const parts = []
  let current = ''
  let inQuotes = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        current += '"'
        i++
      } else {
        inQuotes = !inQuotes
      }
    } else if (ch === ',' && !inQuotes) {
      parts.push(current)
      current = ''
    } else {
      current += ch
    }
  }
  parts.push(current)
  return parts.map(s => s.trim())
}

function readUrlsFromCsv(csvPath) {
  const content = fs.readFileSync(csvPath, 'utf-8')
  const lines = content.split(/\r?\n/).filter(Boolean)
  if (lines.length === 0) return []
  const header = parseCsvLine(lines[0])
  const urlIdx = header.indexOf('url')
  if (urlIdx === -1) return []
  const urls = []
  for (let i = 1; i < lines.length; i++) {
    const cols = parseCsvLine(lines[i])
    const url = cols[urlIdx]
    if (url) urls.push(url)
  }
  return Array.from(new Set(urls))
}

function buildRouteFromUrl(url) {
  try {
    const u = new URL(url)
    const portPart = u.port ? u.port : (u.protocol === 'https:' ? '443' : '80')
    const route = `/ws/${portPart}${u.pathname}`.replace(/\/+$/, '') || '/'
    return { host: u.hostname, port: Number(portPart), path: u.pathname, route, protocol: u.protocol.replace(':','') }
  } catch (e) {
    return null
  }
}

export function createWsApiRouter(options = {}) {
  const router = express.Router()
  const csvPath = path.resolve(__dirname, CSV_RELATIVE)
  const urls = readUrlsFromCsv(csvPath)

  urls.forEach((url) => {
    const info = buildRouteFromUrl(url)
    if (!info) return

    const upstreamBase = `${info.protocol}://${info.host}:${info.port}`

    router.all(info.route, async (req, res) => {
      try {
        const qs = new URLSearchParams(req.query).toString()
        const targetUrl = `${upstreamBase}${info.path}${qs ? `?${qs}` : ''}`
        const method = (req.method || 'GET').toUpperCase()
        const headers = { ...req.headers }
        delete headers['host']

        const response = await axios.request({
          url: targetUrl,
          method,
          headers,
          data: req.body,
          validateStatus: () => true,
          timeout: 15000,
        })

        res.status(response.status)
        for (const [k, v] of Object.entries(response.headers || {})) {
          if (k.toLowerCase() === 'transfer-encoding') continue
          res.setHeader(k, v)
        }
        if (response.data === undefined || response.data === null) {
          res.end()
        } else if (typeof response.data === 'object') {
          res.json(response.data)
        } else {
          res.send(response.data)
        }
      } catch (err) {
        const status = err.response?.status || 502
        res.status(status).json({ error: 'upstream_error', detail: String(err.message || err) })
      }
    })
  })

  // Index of available routes
  router.get('/ws', (req, res) => {
    res.json({ routes: urls.map(u => buildRouteFromUrl(u)?.route).filter(Boolean) })
  })

  return router
}
