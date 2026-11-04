const { test } = require('node:test')
const assert = require('node:assert/strict')
const ts = require('typescript')
const fs = require('node:fs')
const vm = require('node:vm')
const api = {}
const source = fs.readFileSync(`${__dirname}/../src/utils/publishingAccountStatus.ts`, 'utf8')
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: api })

test('three accounts retain distinct verified, saved, and conflicting states', () => {
  const message = '当前登录账号与已绑定账号不一致，请退出并重新登录原账号'
  const results = [
    { status: 'authorized', session_saved: true, login_required: false },
    { status: 'session_saved', login_required: false },
    { status: 'login_required', session_saved: true, login_required: false, message },
  ].map(api.publishingAccountStatus)
  assert.equal(results[0].status, 'authorized')
  assert.equal(results[1].status, 'session_saved')
  assert.equal(results[1].session_saved, true)
  assert.equal(results[2].status, 'identity_mismatch')
  assert.equal(results[2].session_saved, false)
  assert.equal(results[2].publish_ready, false)
  assert.equal(results[2].status_message, message)
})

test('explicit identity conflict takes priority over success and saved flags', () => {
  const result = api.publishingAccountStatus({ status: 'authorized', identity_mismatch: true, session_saved: true })
  assert.equal(result.status, 'identity_mismatch')
  assert.equal(result.session_saved, false)
  assert.equal(result.publish_ready, false)
})

test('expired and loading sessions never inherit a publishable saved badge', () => {
  const result = api.publishingAccountStatus({ status: 'login_required', session_saved: true, login_required: true, message: '登录已过期' })
  assert.equal(result.status, 'authorizing')
  assert.equal(result.session_saved, false)
  assert.equal(result.status_message, '登录已过期')
})

test('verified saved accounts remain publishable without keeping their browser open', () => {
  for (let i = 0; i < 3; i++) {
    const result = api.publishingAccountStatus({ status: 'session_saved', login_required: false, publish_ready: true })
    assert.equal(result.status, 'session_saved')
    assert.equal(result.session_saved, true)
    assert.equal(result.publish_ready, true)
  }
  assert.equal(api.publishingAccountStatus({ status: 'session_saved' }).publish_ready, false)
})
