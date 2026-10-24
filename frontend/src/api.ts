/** Proxies can return empty or HTML error bodies; never expose JSON parser errors. */
export async function readApiResponse<T>(response: Response): Promise<T> {
  const text = await response.text()
  let body: unknown
  try { body = text.trim() ? JSON.parse(text) : undefined } catch { body = undefined }
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : undefined
    if (typeof detail === 'string') throw new Error(detail)
    if (response.status === 413) throw new Error('O arquivo ultrapassa o limite de envio. Escolha um arquivo menor ou ajuste o limite do servidor.')
    if (response.status >= 500) throw new Error('O serviço de análise está indisponível. Confira se a API está em execução e tente novamente.')
    throw new Error(`Não foi possível processar a solicitação (HTTP ${response.status}). Tente novamente.`)
  }
  if (!body || typeof body !== 'object') throw new Error('O servidor retornou uma resposta vazia ou inválida. Tente novamente; se continuar, reinicie a API.')
  return body as T
}

export function uploadSizeError(size: number, limit: number): string | null {
  if (size <= limit) return null
  const mb = (value: number) => (value / 1024 / 1024).toLocaleString('pt-BR', { maximumFractionDigits: 1 })
  return `O arquivo tem ${mb(size)} MB e o limite de envio é ${mb(limit)} MB. Escolha um arquivo menor.`
}
