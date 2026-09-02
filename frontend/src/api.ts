const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export type CharacterApi = {
  id: string
  version: number
  name: string
  nickname: string | null
  age: number | null
  occupation: string
  gender: 'male' | 'female' | 'unspecified'
  concept: string
  persona: string
  additional_prompt: string
  image_url: string | null
  traits: string[]
  speech_style: string
  response_length: string
  relationship_style: string
  voice_label: string
  typecast_voice_id: string | null
}

export type CharacterWriteApi = Omit<CharacterApi, 'id' | 'version' | 'image_url'>


export type ScenarioDraftApi = {
  id: string
  mode: 'A' | 'B' | 'C'
  title: string
  summary: string
  opening_guide: string
  character_ids: string[]
  editor_state: Record<string, unknown>
  status: 'DRAFT' | 'PUBLISHED'
}

export type ScenarioDraftWriteApi = Omit<ScenarioDraftApi, 'id' | 'status'> & { publish: boolean }
export type TypecastVoiceApi = {
  voice_id: string
  voice_name: string
  gender: string | null
  age: string | null
  use_cases: string[]
  voice_type: string | null
}
export type ConversationApi = {
  id: string
  mode: 'TALK'
  status: 'ACTIVE' | 'COMPLETED'
  character_ids: string[]
}

export type MessageApi = {
  id: string
  speaker_type: 'USER' | 'CHARACTER' | 'SYSTEM'
  speaker_id: string | null
  content: string
  input_mode: 'TEXT' | 'VOICE' | 'SYSTEM'
}

export type SceneTurnApi = {
  speaker_id: string
  to: string
  emotion: string
  text: string
}

export type ShareSuggestionApi = {
  memory_id: string
  from_character_id: string
  to_character_id: string
  content_preview: string
}

export type MessageExchangeApi = {
  user_message: MessageApi
  assistant_messages: MessageApi[]
  scene_plan: { turns: SceneTurnApi[] }
  share_suggestions: ShareSuggestionApi[]
}

export type WorkflowStreamEvent = {
  event: 'message_accepted' | 'workflow_started' | 'node_completed' | 'workflow_completed' | 'error' | string
  node?: string
  status?: 'started' | 'completed' | 'failed' | string
  details?: {
    retrieved_memory_ids?: string[]
    prompt_memory_ids?: string[]
    retrieved_count?: number
    turn_count?: number
    speaker_count?: number
  }
  user_message?: MessageApi
  exchange?: MessageExchangeApi
  observation?: Record<string, unknown>
  message?: string
}

export type MemorySharingMode = 'NONE' | 'SHARED' | 'FIRST_ONLY' | 'SECOND_ONLY'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json' },
    })
  } catch {
    throw new Error(`백엔드에 연결할 수 없습니다: ${API_BASE_URL}`)
  }
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body}`)
  }
  return response.json() as Promise<T>
}

export async function listCharacters(): Promise<CharacterApi[]> {
  const response = await request<{ items: CharacterApi[] }>('/api/v1/characters')
  return response.items
}

export function createCharacter(value: CharacterWriteApi): Promise<CharacterApi> {
  return request('/api/v1/characters', {
    method: 'POST',
    body: JSON.stringify(value),
  })
}

export function updateCharacter(id: string, value: CharacterWriteApi): Promise<CharacterApi> {
  return request(`/api/v1/characters/${encodeURIComponent(id)}`, {
    method: 'PUT',
    body: JSON.stringify(value),
  })
}

export function createConversation(
  characterIds: string[],
  openingSpeakerId: string,
  openingMessage: string,
  memorySharingMode: MemorySharingMode = 'NONE',
): Promise<ConversationApi> {
  return request('/api/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({
      mode: 'TALK',
      character_ids: characterIds,
      opening_message: { speaker_id: openingSpeakerId, content: openingMessage },
      memory_sharing_mode: memorySharingMode,
    }),
  })
}

export function sendTextMessage(
  conversationId: string,
  content: string,
): Promise<MessageExchangeApi> {
  return request(`/api/v1/conversations/${conversationId}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, input_mode: 'TEXT' }),
  })
}

export async function sendTextMessageStream(
  conversationId: string,
  content: string,
  onEvent: (event: WorkflowStreamEvent) => void,
): Promise<MessageExchangeApi> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/conversations/${conversationId}/messages/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ content, input_mode: 'TEXT' }),
    })
  } catch {
    throw new Error(`백엔드에 연결할 수 없습니다: ${API_BASE_URL}`)
  }
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body}`)
  }
  if (!response.body) throw new Error('스트리밍 응답을 읽을 수 없습니다.')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let exchange: MessageExchangeApi | undefined

  const consumeBlock = (block: string) => {
    let eventName = 'message'
    const dataLines: string[] = []
    for (const line of block.split(/\r?\n/)) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) return
    let parsed: WorkflowStreamEvent
    try {
      parsed = JSON.parse(dataLines.join('\n')) as WorkflowStreamEvent
    } catch {
      return
    }
    onEvent({ ...parsed, event: parsed.event || eventName })
    if (parsed.event === 'error') throw new Error(parsed.message || '응답 생성에 실패했습니다.')
    if (parsed.event === 'workflow_completed' && parsed.exchange) exchange = parsed.exchange
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })
    const blocks = buffer.split(/\r?\n\r?\n/)
    buffer = blocks.pop() ?? ''
    blocks.forEach(consumeBlock)
    if (done) break
  }
  if (buffer.trim()) consumeBlock(buffer)
  if (!exchange) throw new Error('스트리밍 응답에 최종 대화 결과가 없습니다.')
  return exchange
}

export async function getProfile(): Promise<string> {
  const response = await request<{ display_name: string }>('/api/v1/profile')
  return response.display_name
}

export async function updateProfile(displayName: string): Promise<string> {
  const response = await request<{ display_name: string }>('/api/v1/profile', {
    method: 'PUT',
    body: JSON.stringify({ display_name: displayName }),
  })
  return response.display_name
}

export async function shareMemory(memoryId: string, grantToCharacterId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/v1/memories/${memoryId}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ grant_to_character_id: grantToCharacterId, can_disclose_to: true }),
  })
  if (!response.ok) {
    const body = await response.text()
    throw new Error(`API ${response.status}: ${body}`)
  }
}

export async function fetchSpeechAudio(
  speakerId: string,
  text: string,
  emotion: string,
  voiceId?: string,
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tts/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      speaker_id: speakerId,
      text,
      emotion,
      voice_id: voiceId,
      audio_format: 'mp3',
    }),
  })
  if (!response.ok) {
    const detail = await response.text()
    throw new Error(`TTS API ${response.status}${detail ? `: ${detail}` : ''}`)
  }
  return response.blob()
}
export async function listTypecastVoices(filters?: { gender?: 'male' | 'female'; age?: string }): Promise<TypecastVoiceApi[]> {
  const query = new URLSearchParams()
  if (filters?.gender) query.set('gender', filters.gender)
  if (filters?.age) query.set('age', filters.age)
  const suffix = query.size > 0 ? `?${query.toString()}` : ''
  return request(`/api/v1/tts/voices${suffix}`)
}
export async function uploadCharacterPortrait(id: string, file: File): Promise<CharacterApi> {
  const body = new FormData()
  body.append('file', file)
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/characters/${encodeURIComponent(id)}/portrait`, {
      method: 'POST',
      body,
    })
  } catch {
    throw new Error(`백엔드에 연결할 수 없습니다: ${API_BASE_URL}`)
  }
  if (!response.ok) {
    throw new Error(`이미지 저장 API ${response.status}: ${await response.text()}`)
  }
  return response.json() as Promise<CharacterApi>
}

export function apiAssetUrl(path: string | null): string | undefined {
  if (!path) return undefined
  return path.startsWith('http') ? path : `${API_BASE_URL}${path}`
}
export function listScenarioDrafts(): Promise<ScenarioDraftApi[]> {
  return request('/api/v1/scenarios')
}
export function getScenarioDraft(id: string): Promise<ScenarioDraftApi> {
  return request(`/api/v1/scenarios/${encodeURIComponent(id)}`)
}

export function createScenarioDraft(value: ScenarioDraftWriteApi): Promise<ScenarioDraftApi> {
  return request('/api/v1/scenarios', { method: 'POST', body: JSON.stringify(value) })
}

export function updateScenarioDraft(id: string, value: ScenarioDraftWriteApi): Promise<ScenarioDraftApi> {
  return request(`/api/v1/scenarios/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(value) })
}


