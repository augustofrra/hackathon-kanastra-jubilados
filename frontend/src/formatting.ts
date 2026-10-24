export const integerBr = (value: number) => value.toLocaleString('pt-BR')
export const countBr = (value: number, singular: string, plural = `${singular}s`) => `${integerBr(value)} ${Math.abs(value) === 1 ? singular : plural}`
export const daysBr = (value: number) => countBr(value, 'dia')
export const fileSizeBr = (bytes: number) => `${(bytes / 1024 / 1024).toLocaleString('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} MB`
export const moneyBr = (value: string | null) => {
  if (value === null) return '—'
  const [whole, cents = '00'] = value.split('.')
  return `R$ ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${cents.padEnd(2, '0')}`
}
export const cnpjBr = (value: string) => value.replace(/\D/g, '').replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5')
