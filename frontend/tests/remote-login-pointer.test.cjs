const { test } = require('node:test')
const assert = require('node:assert/strict')
const ts = require('typescript')
const fs = require('node:fs')
const vm = require('node:vm')
const source = fs.readFileSync(`${__dirname}/../src/utils/remoteLoginPointer.ts`, 'utf8')
const api = {}
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: api, Math })
const plain = value => JSON.parse(JSON.stringify(value))

test('small hand movement remains a click on a reduced cloud view', () => {
  const rect = {left:20,top:100,width:360,height:240}
  const start = {id:1,clientX:180,clientY:200,...api.loginPoint(180,200,rect,{width:1440,height:960})}
  const end = api.loginPoint(185,202,rect,{width:1440,height:960})
  assert.deepEqual(plain(api.loginPointerAction(start,end,185,202)),{kind:'click',x:640,y:400})
})
test('intentional dragging preserves start and end remote coordinates', () => {
  const start = {id:1,clientX:100,clientY:100,x:200,y:200}
  assert.deepEqual(plain(api.loginPointerAction(start,{x:400,y:200},200,100)),{kind:'drag',x:200,y:200,end_x:400,end_y:200})
})
test('coordinates respect actual viewport size and image edges', () => {
  const rect = {left:10,top:20,width:720,height:480}
  assert.deepEqual(plain(api.loginPoint(370,260,rect,{width:1440,height:960})),{x:720,y:480})
  assert.deepEqual(plain(api.loginPoint(-100,-100,rect,{width:1440,height:960})),{x:0,y:0})
  assert.deepEqual(plain(api.loginPoint(2000,2000,rect,{width:1440,height:960})),{x:1439,y:959})
})
