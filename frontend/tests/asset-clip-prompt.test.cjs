const { test } = require('node:test')
const assert = require('node:assert/strict')
const ts = require('typescript')
const fs = require('node:fs')
const vm = require('node:vm')
const api = {}
const source = fs.readFileSync(`${__dirname}/../src/utils/assetClipPrompt.ts`, 'utf8')
vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports: api })
const asset = (vision = {}) => ({ name: '不能当事实的文件名.jpg', metadata: { vision_analysis: vision } })

test('recognized people receive early visible subject action and actual image facts', () => {
  const prompt = api.initialClipPrompt(asset({ status: 'completed', people_visible: true, visual_description: '一位游客站在湖边' }))
  assert.ok(prompt.includes('一位游客站在湖边'))
  assert.ok(prompt.includes('真人是动作主体'))
  assert.ok(prompt.includes('前0.3秒'))
  assert.ok(prompt.includes('前3秒'))
  assert.ok(prompt.includes('不能只有镜头拉远'))
  assert.ok(prompt.length <= 2000)
})

test('explicitly empty scenery never asks for character animation', () => {
  const prompt = api.defaultClipPrompt(asset({ people_visible: false, caption: '静谧湖景' }))
  assert.ok(prompt.includes('静谧湖景'))
  assert.ok(prompt.includes('短距离侧移'))
  assert.ok(!prompt.includes('自然转头'))
})

test('missing or pending vision uses conditional guidance without invented filename facts', () => {
  for (const vision of [{}, { status: 'pending', visual_description: '过期场景' }]) {
    const prompt = api.defaultClipPrompt(asset(vision))
    assert.ok(prompt.includes('如图片中有真人'))
    assert.ok(!prompt.includes('不能当事实的文件名'))
    assert.ok(!prompt.includes('过期场景'))
  }
  assert.ok(api.defaultClipPrompt({ source_description: '用户确认的场景' }).includes('用户确认的场景'))
})

test('regeneration keeps previous creative instructions, falling back only when empty', () => {
  const image = asset({ people_visible: true })
  assert.equal(api.initialClipPrompt(image, { metadata: { clip_library: { prompt: '保持原姿态，抬手展示已有商品' } } }), '保持原姿态，抬手展示已有商品')
  assert.equal(api.initialClipPrompt(image, { metadata: { clip_library: { prompt: '  ' } } }), api.defaultClipPrompt(image))
  assert.ok(api.defaultClipPrompt(asset({ visual_description: '图'.repeat(3000) })).length <= 2000)
})
