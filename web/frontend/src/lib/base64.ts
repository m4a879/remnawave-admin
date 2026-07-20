/** UTF-8-безопасный base64 (encodedTemplateYaml панели и т.п.). */

export function b64DecodeUtf8(b64: string): string {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new TextDecoder().decode(bytes)
}

export function b64EncodeUtf8(text: string): string {
  const bytes = new TextEncoder().encode(text)
  let bin = ''
  // чанки — String.fromCharCode(...huge) роняет стек на больших строках
  const CHUNK = 0x8000
  for (let i = 0; i < bytes.length; i += CHUNK) {
    bin += String.fromCharCode(...bytes.subarray(i, i + CHUNK))
  }
  return btoa(bin)
}
