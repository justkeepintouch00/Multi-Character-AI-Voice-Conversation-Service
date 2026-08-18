const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/$/, '')

export type CharacterApi = {
  id: string
  version: number
  name: string
  nickname: string | null
  concept: string
  persona: string
  traits: string[]
  speech_style: string
  response_length: string
  relationship_style: string
  voice_label: string
}

export type CharacterWriteApi = Omit<CharacterApi, 'id' | 'version'>

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

export type MessageExchangeApi = {
  user_message: MessageApi
  assistant_messages: MessageApi[]
  scene_plan: { turns: SceneTurnApi[] }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json' },
  })
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
): Promise<ConversationApi> {
  return request('/api/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({
      mode: 'TALK',
      character_ids: characterIds,
      opening_message: { speaker_id: openingSpeakerId, content: openingMessage },
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

export async function fetchSpeechAudio(
  speakerId: string,
  text: string,
  emotion: string,
): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}/api/v1/tts/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      speaker_id: speakerId,
      text,
      emotion,
      audio_format: 'mp3',
    }),
  })
  if (!response.ok) {
    throw new Error(`TTS API ${response.status}`)
  }
  return response.blob()
}
