import axios from 'axios'
import express from 'express'

// Explicit upstream URLs (extracted from the first column of url_to_responses.csv)
const UPSTREAM = {
  system: 'http://192.168.50.100:2400/system',
  devices: 'http://192.168.50.100:2400/devices',
  devicesMonitoringEvents: 'http://192.168.50.100:2400/devices/monitoring-events',
  devicesCommands: 'http://192.168.50.100:2400/devices/commands',
  systemStatus: 'http://192.168.50.100:2400/system/status',
  operationModesActive: 'http://192.168.50.100:2400/operation-modes/active',
  settingsGeneral: 'http://192.168.50.100:2400/settings/general',
  alerts: 'http://192.168.50.100:2400/alerts',
  systemState: 'http://192.168.50.100:2400/system/state',
  settingsSleepModeTimeout: 'http://192.168.50.100:2600/settings/sleepModeTimeout',
  generatorProfiles: 'http://192.168.50.100:2400/generator-profiles',
  operationModes: 'http://192.168.50.100:2400/operation-modes',
  generatorProfilesStatus: 'http://192.168.50.100:2400/generator-profiles/status',
}

async function fetchUpstream(url, req) {
  const qs = new URLSearchParams(req?.query || {}).toString()
  const target = qs ? `${url}?${qs}` : url
  const res = await axios.get(target, { validateStatus: () => true, timeout: 15000 })
  return res
}

export const api = {
  async system(req) { return fetchUpstream(UPSTREAM.system, req) },
  async devices(req) { return fetchUpstream(UPSTREAM.devices, req) },
  async devicesMonitoringEvents(req) { return fetchUpstream(UPSTREAM.devicesMonitoringEvents, req) },
  async devicesCommands(req) { return fetchUpstream(UPSTREAM.devicesCommands, req) },
  async systemStatus(req) { return fetchUpstream(UPSTREAM.systemStatus, req) },
  async operationModesActive(req) { return fetchUpstream(UPSTREAM.operationModesActive, req) },
  async settingsGeneral(req) { return fetchUpstream(UPSTREAM.settingsGeneral, req) },
  async alerts(req) { return fetchUpstream(UPSTREAM.alerts, req) },
  async systemState(req) { return fetchUpstream(UPSTREAM.systemState, req) },
  async settingsSleepModeTimeout(req) { return fetchUpstream(UPSTREAM.settingsSleepModeTimeout, req) },
  async generatorProfiles(req) { return fetchUpstream(UPSTREAM.generatorProfiles, req) },
  async operationModes(req) { return fetchUpstream(UPSTREAM.operationModes, req) },
  async generatorProfilesStatus(req) { return fetchUpstream(UPSTREAM.generatorProfilesStatus, req) },
}

export function createExplicitApiRouter() {
  const router = express.Router()

  const map = [
    ['get', '/api/system', api.system],
    ['get', '/api/devices', api.devices],
    ['get', '/api/devices/monitoring-events', api.devicesMonitoringEvents],
    ['get', '/api/devices/commands', api.devicesCommands],
    ['get', '/api/system/status', api.systemStatus],
    ['get', '/api/operation-modes/active', api.operationModesActive],
    ['get', '/api/settings/general', api.settingsGeneral],
    ['get', '/api/alerts', api.alerts],
    ['get', '/api/system/state', api.systemState],
    ['get', '/api/settings/sleepModeTimeout', api.settingsSleepModeTimeout],
    ['get', '/api/generator-profiles', api.generatorProfiles],
    ['get', '/api/operation-modes', api.operationModes],
    ['get', '/api/generator-profiles/status', api.generatorProfilesStatus],
  ]

  map.forEach(([method, path, handler]) => {
    router[method](path, async (req, res) => {
      try {
        const upstreamRes = await handler(req)
        res.status(upstreamRes.status)
        if (typeof upstreamRes.data === 'object') {
          res.json(upstreamRes.data)
        } else {
          res.send(upstreamRes.data)
        }
      } catch (err) {
        res.status(502).json({ error: 'upstream_error', detail: String(err.message || err) })
      }
    })
  })

  router.get('/api', (req, res) => {
    res.json({ endpoints: map.map(([, p]) => p) })
  })

  return router
}


