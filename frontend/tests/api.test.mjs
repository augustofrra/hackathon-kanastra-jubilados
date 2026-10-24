import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import ts from 'typescript'

const source = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')
const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const { readApiResponse, uploadSizeError } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`)

test('preserves successful results and structured API errors', async () => {
  assert.deepEqual(await readApiResponse(Response.json({ lote: { aprovadas: 3 } })), { lote: { aprovadas: 3 } })
  await assert.rejects(readApiResponse(Response.json({ detail: 'O limite é 1 MB.' }, { status: 413 })), /O limite é 1 MB/)
})
test('handles empty and HTML responses from upload proxies', async () => {
  await assert.rejects(readApiResponse(new Response('', { status: 413 })), /ultrapassa o limite/)
  await assert.rejects(readApiResponse(new Response('<html>Bad gateway</html>', { status: 502 })), /serviço de análise está indisponível/)
  await assert.rejects(readApiResponse(new Response('', { status: 500 })), /serviço de análise está indisponível/)
  await assert.rejects(readApiResponse(new Response('')), /resposta vazia ou inválida/)
})
test('checks the limit advertised by the API, with an inclusive boundary', () => {
  assert.equal(uploadSizeError(20 * 1024 ** 2, 50 * 1024 ** 2), null)
  assert.equal(uploadSizeError(50 * 1024 ** 2, 50 * 1024 ** 2), null)
  assert.match(uploadSizeError(20 * 1024 ** 2, 10 * 1024 ** 2), /limite de envio é 10 MB/)
})

const formattingSource = readFileSync(new URL('../src/formatting.ts', import.meta.url), 'utf8')
const compiled = ts.transpileModule(formattingSource, { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } })
const formats = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputText).toString('base64')}`)
test('formats counts, days, money, CNPJ and file sizes in pt-BR', () => {
  assert.equal(formats.integerBr(100554), '100.554')
  assert.equal(formats.daysBr(1), '1 dia')
  assert.equal(formats.daysBr(2), '2 dias')
  assert.equal(formats.daysBr(-1), '-1 dia')
  assert.equal(formats.countBr(1, 'nota'), '1 nota')
  assert.equal(formats.fileSizeBr(20276472), '19,3 MB')
  assert.equal(formats.moneyBr('100554.00'), 'R$ 100.554,00')
  assert.equal(formats.moneyBr('1234567890.12'), 'R$ 1.234.567.890,12')
  assert.equal(formats.cnpjBr('92234400000180'), '92.234.400/0001-80')
})
