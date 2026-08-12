import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createCharacter,
  createConversation,
  listCharacters,
  sendTextMessage,
  updateCharacter,
  type CharacterApi,
  type MessageApi,
} from './api'
import './App.css'

type Page = 'home' | 'characters' | 'scenarios' | 'builder' | 'characterEditor' | 'intro' | 'run' | 'result'
type Mode = 'A' | 'B' | 'C'
type BuilderSection = 'overview' | 'characters' | 'flow' | 'endings' | 'rules' | 'preview'

type Character = {
  id: string
  name: string
  nickname: string
  concept: string
  persona: string
  traits: string[]
  speech: string
  length: string
  relation: string
  voice: string
  accent: string
  updated: string
  image?: string
}

type Scenario = {
  id: string
  mode: Mode
  title: string
  summary: string
  characterNames: string[]
  duration: string
  published: boolean
  plays: number
  coverImage?: string
}

type TurnDraft = { situation: string; line: string; userGoal: string; background: string; backgroundImage?: string }
type EndingDraft = { name: string; description: string; condition: string }
type FlowBranchDraft = {
  id: string
  label: string
  responseType: string
  condition: string
  reactionTone: string
  reactionGuide: string
  affinity: number
  trust: number
  boundary: number
  nextScene: string
  fallback: boolean
}
type ScenarioDraft = {
  title: string
  summary: string
  openingGuide: string
  estimatedDuration: string
  practiceType: string
  characters: string
  useAffinity: boolean
  turns: TurnDraft[]
  endings: EndingDraft[]
  background: string
  coverImage: string
}

type ScenarioCharacterDraft = {
  id: string
  name: string
  concept: string
  traits: string[]
  speech: string
  relation: string
  voice: string
  image?: string
}

type ResultData = {
  scenario: Scenario
  ending: string
  story: string
  reason: string
  effective: string[]
  evidence: string
  missed?: string
  remember: string
  reaction: string
  relation: string
}

type VoiceState = 'starting' | 'listening' | 'unsupported' | 'denied'
type RecognitionResultEvent = {
  resultIndex: number
  results: { [index: number]: { 0: { transcript: string }; isFinal: boolean }; length: number }
}
type RecognitionErrorEvent = { error: string }
type RecognitionInstance = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onstart: (() => void) | null
  onresult: ((event: RecognitionResultEvent) => void) | null
  onerror: ((event: RecognitionErrorEvent) => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type RecognitionConstructor = new () => RecognitionInstance

declare global {
  interface Window {
    SpeechRecognition?: RecognitionConstructor
    webkitSpeechRecognition?: RecognitionConstructor
  }
}

const initialCharacters: Character[] = [
  {
    id: 'haru', name: '하루', nickname: '하루',
    concept: '동네 편의점에서 야간 아르바이트를 한다. 장난이 많고 매운 음식을 좋아하며, 사용자가 결정을 미루면 가볍게 등을 떠민다.',
    persona: '친한 친구처럼 반말을 사용한다. 일상적인 말에는 장난스럽고 솔직하게 반응하며 과도한 상담 문구를 사용하지 않는다.',
    traits: ['장난스러운', '솔직한', '활발한'], speech: '반말', length: '보통', relation: '장난을 많이 치는 동생',
    voice: '밝고 또렷한 목소리', accent: 'violet', updated: '오늘 수정', image: '/assets/20260811_1726_haru_profile.png',
  },
  {
    id: 'lumi', name: '루미', nickname: '',
    concept: '오래된 골목에서 시계 공방을 운영한다. 식사를 자주 거르고 밤늦게 혼자 산책하며, 조용하지만 상대의 말을 오래 기억한다.',
    persona: '차분하고 섬세하지만 모든 말을 고민 상담으로 취급하지 않는다. 사용자의 표현에 구체적이고 자연스럽게 반응한다.',
    traits: ['다정한', '차분한', '섬세한'], speech: '관계에 따라 변화', length: '보통', relation: '차분하게 이끌어주는 선배',
    voice: '낮고 차분한 목소리', accent: 'blue', updated: '어제 수정',
  },
  {
    id: 'jiyoon', name: '지윤', nickname: '지유',
    concept: '동아리의 총무를 맡고 있다. 의견을 강하게 주장하지 않지만 시간과 음식 제한처럼 실제로 지켜야 할 조건을 꼼꼼하게 기억한다.',
    persona: '현실적인 조건을 짧게 확인하며 사용자를 평가하거나 결정을 대신하지 않는다.',
    traits: ['차분한', '솔직한', '섬세한'], speech: '반말', length: '짧게 말함', relation: '조용히 곁을 지키는 동료',
    voice: '부드럽고 편안한 목소리', accent: 'mint', updated: '3일 전 수정',
  },
]

const initialScenarios: Scenario[] = [
  { id: 'snack', mode: 'A', title: '오늘의 간식 선발전', summary: '제한 시간 안에 간식을 고르고 자기 이유를 분명하게 말해보는 짧은 연습', characterNames: ['하루'], duration: '약 5분', published: true, plays: 128, coverImage: '/assets/20260812_1414_snack_selection_scene_clean.png' },
  { id: 'lunch', mode: 'B', title: '오늘 점심은 반드시 정한다', summary: '지윤이 전해준 서로 다른 의견과 제한 조건을 확인해 실행할 수 있는 결정을 만드는 상황', characterNames: ['지윤'], duration: '약 8분', published: true, plays: 84 },
  { id: 'first-talk', mode: 'C', title: '공방이 문을 닫은 뒤', summary: '말할 준비가 될 때까지 루미의 일상을 따라가며 천천히 대화를 시작하는 이야기', characterNames: ['루미'], duration: '자유 대화', published: true, plays: 203 },
]

const initialDrafts: Record<Mode, ScenarioDraft> = {
  A: {
    title: '오늘의 간식 선발전', summary: '제한 시간 안에 간식을 고르고 이유를 말해보자!', openingGuide: '두 가지 간식 중 하나를 직접 고르고, 캐릭터에게 선택한 이유를 말하는 연습입니다.', estimatedDuration: '약 5분', practiceType: '빠르게 결정하기', characters: '하루', useAffinity: true,
    background: '동네 편의점 · 과자 코너', coverImage: '/assets/20260812_1414_snack_selection_scene_clean.png',
    turns: [
      { situation: '하루가 두 가지 과자를 들고 사용자를 바라본다.', line: '매운맛이랑 치즈맛 중 하나 골라줘. 이유도 바로 말해야지?', userGoal: '둘 중 하나를 선택하고 이유를 말하기', background: '편의점 과자 코너', backgroundImage: '/assets/20260812_1414_snack_selection_scene_clean.png' },
      { situation: '하루가 네 선택을 기다리며 궁금해한다.', line: '오~ 이유도 궁금한데? 왜 그걸 골랐어?', userGoal: '선택한 이유를 구체적으로 설명하기', background: '편의점 과자 코너', backgroundImage: '/assets/20260812_1414_snack_selection_scene_clean.png' },
      { situation: '하루가 간식을 계산대로 가져간다.', line: '좋아, 그럼 이거나 같이 먹으면서 얘기하자.', userGoal: '결정에 동의하거나 다른 의견 말하기', background: '편의점 계산대', backgroundImage: '/assets/20260812_1414_snack_selection_scene_clean.png' },
    ],
    endings: [
      { name: '불닭 동맹', description: '매운맛을 자주 선택하고 자기 이유를 분명하게 말해 하루와 취향이 잘 맞았다.', condition: '매운맛 선택을 반복하고 근거를 구체적으로 설명했을 때' },
      { name: '치즈 좋아 청년', description: '하루의 권유에도 자기 취향을 유지하면서 대화를 자연스럽게 이어갔다.', condition: '치즈맛을 선택하고 자기 취향을 일관되게 설명했을 때' },
      { name: '편의점 12바퀴', description: '선택을 계속 미루다 다른 코너까지 둘러보고 다시 과자 코너로 돌아왔다.', condition: '결정 회피가 반복되었을 때' },
    ],
  },
  B: {
    title: '오늘 점심은 반드시 정한다', summary: '지윤과 대화하며 엇갈리는 의견과 제한 조건을 조율해 점심 메뉴를 결정해보자.', openingGuide: '지윤이 전달하는 여러 사람의 의견을 정리하고, 시간과 음식 제한까지 반영해 실행 가능한 결정을 만듭니다.', estimatedDuration: '약 8분', practiceType: '의견 조율하기', characters: '지윤', useAffinity: true,
    background: '대학교 동아리방 · 점심시간', coverImage: '',
    turns: [
      { situation: '정오가 지났지만 동아리의 점심 메뉴가 아직 정해지지 않았다.', line: '민수는 국밥, 하루는 파스타를 원하고 나는 10분 안에 나가고 싶어. 너라면 어떻게 정할래?', userGoal: '전달받은 의견을 정리하고 자신의 제안을 말하기', background: '동아리방' },
      { situation: '파스타로 의견이 모이지만 지윤이 메뉴판 앞에서 멈춘다.', line: '여기 견과류 들어간 메뉴가 꽤 많은데… 내가 먹을 수 있는 게 있나?', userGoal: '앞서 나온 제한 조건을 확인하고 결정을 보완하기', background: '식당 앞' },
      { situation: '모두가 최종 결정을 기다린다.', line: '시간 안에 실제로 갈 수 있는 선택을 정리해줘.', userGoal: '실행 가능한 최종안을 제시하기', background: '식당 거리' },
    ],
    endings: [
      { name: '모두가 먹을 수 있는 식당', description: '취향뿐 아니라 음식 제한과 시간까지 확인해 실행 가능한 선택을 만들었다.', condition: '모든 등장인물의 제한 조건을 확인하고 최종안을 제시했을 때' },
      { name: '식당 앞에서 다시 고민하기', description: '메뉴는 빠르게 정했지만 앞에서 나온 음식 제한이 최종 선택에 반영되지 않았다.', condition: '취향만 반영하고 제한 조건을 다시 확인하지 않았을 때' },
      { name: '아무거나 원정대', description: '선택을 서로에게 넘기는 동안 점심시간이 계속 지나갔다.', condition: '결정 회피가 반복되었을 때' },
    ],
  },
  C: {
    title: '공방이 문을 닫은 뒤', summary: '루미의 일상을 따라가거나 내 이야기부터 시작할 수 있는 점진적 대화 진입', openingGuide: '한 개의 공통 시작 장면에서 대표 화자가 먼저 말을 건넵니다. 다른 캐릭터는 대화 흐름에 맞춰 순차적으로 참여합니다.', estimatedDuration: '자유 진행', practiceType: '평가 없는 자유 대화', characters: '루미', useAffinity: false,
    background: '시계 공방 · 저녁', coverImage: '',
    turns: [
      { situation: '루미가 공방 문을 닫으며 사용자를 반긴다.', line: '처음부터 말하려니 어색할 수 있겠다. 내 이야기만 먼저 들어도 괜찮아.', userGoal: '내 이야기부터 할지, 루미를 더 알아갈지 선택하기', background: '시계 공방' },
      { situation: '루미가 오늘 점심을 놓쳤다고 이야기한다.', line: '따뜻한 수프랑 샌드위치 중에 뭘 고를 것 같아?', userGoal: '부담이 낮은 선택으로 대화에 참여하기', background: '공방 앞 골목' },
    ], endings: [],
  },
}

const initialFlowBranches: Record<Mode, FlowBranchDraft[]> = {
  A: [
    { id: 'a-clear-reason', label: '선택 + 이유 설명', responseType: '명확한 선택과 이유', condition: '사용자가 하나를 고르고 구체적인 이유를 말함', reactionTone: '장난스럽게 인정', reactionGuide: '선택을 인정하고 이유의 핵심 단어에 짧게 반응한 뒤 다음 비교를 제시한다.', affinity: 4, trust: 3, boundary: 0, nextScene: '장면 2 · 중간 비교', fallback: false },
    { id: 'a-clear-only', label: '선택만 말함', responseType: '명확한 선택', condition: '선택은 했지만 이유가 없거나 매우 짧음', reactionTone: '가볍게 재질문', reactionGuide: '선택을 긍정한 뒤 이유를 한 번만 묻는다. 압박하거나 정답을 암시하지 않는다.', affinity: 1, trust: 1, boundary: 0, nextScene: '장면 1 · 이유 확인', fallback: false },
    { id: 'a-avoid', label: '결정을 미룸', responseType: '회피 또는 책임 전가', condition: '“아무거나”, “네가 골라”처럼 선택을 상대에게 넘김', reactionTone: '장난스럽지만 단호하게', reactionGuide: '캐릭터 성격을 유지하면서 선택권을 사용자에게 다시 돌려준다.', affinity: -2, trust: -1, boundary: 0, nextScene: '장면 1 · 다시 선택', fallback: false },
    { id: 'a-question', label: '캐릭터에게 질문', responseType: '상대에게 질문', condition: '선택 전에 캐릭터의 취향이나 이유를 질문함', reactionTone: '솔직하게 답변', reactionGuide: '자신의 취향을 짧게 답한 뒤 사용자의 선택을 다시 요청한다.', affinity: 1, trust: 2, boundary: 0, nextScene: '장면 1 · 선택 반환', fallback: false },
    { id: 'a-fallback', label: '그 밖의 응답', responseType: '분류되지 않은 응답', condition: '위 조건에 해당하지 않거나 맥락이 불명확함', reactionTone: '차분하게 맥락 확인', reactionGuide: '사용자의 말을 추측해서 단정하지 말고 현재 선택지를 다시 짧게 안내한다.', affinity: 0, trust: 0, boundary: 0, nextScene: '장면 1 · 맥락 확인', fallback: true },
  ],
  B: [
    { id: 'b-coordinate', label: '조건까지 조율', responseType: '의견 조율과 조건 확인', condition: '여러 의견과 시간·음식 제한을 함께 반영함', reactionTone: '신뢰하며 동의', reactionGuide: '제안이 실제로 가능한지 확인하고 캐릭터가 동의하는 이유를 말한다.', affinity: 3, trust: 5, boundary: 0, nextScene: '장면 3 · 최종 결정', fallback: false },
    { id: 'b-majority', label: '다수 의견만 반영', responseType: '빠른 다수결', condition: '다수의 취향은 반영했지만 제한 조건을 확인하지 않음', reactionTone: '결정은 인정하고 우려 표현', reactionGuide: '결정 속도는 인정하되 빠진 제한 조건을 구체적으로 한 번 확인한다.', affinity: 0, trust: -1, boundary: 0, nextScene: '장면 2 · 조건 재확인', fallback: false },
    { id: 'b-avoid', label: '결정을 넘김', responseType: '결정 회피', condition: '다른 사람에게 최종 결정을 맡기고 제안을 하지 않음', reactionTone: '차분하게 책임 반환', reactionGuide: '비난하지 않고 사용자가 실행 가능한 제안을 하나 말하도록 요청한다.', affinity: -1, trust: -2, boundary: 0, nextScene: '장면 1 · 제안 요청', fallback: false },
    { id: 'b-fallback', label: '그 밖의 응답', responseType: '분류되지 않은 응답', condition: '의견 조율과 관련 없는 답변이 들어옴', reactionTone: '현재 조건 다시 정리', reactionGuide: '이미 나온 의견과 제한 조건만 간단히 다시 말하고 제안을 요청한다.', affinity: 0, trust: 0, boundary: 0, nextScene: '장면 1 · 맥락 확인', fallback: true },
  ],
  C: [
    { id: 'c-user-story', label: '내 이야기부터 시작', responseType: '사용자 자기 이야기', condition: '사용자가 자신의 일상이나 감정을 먼저 이야기함', reactionTone: '서두르지 않고 경청', reactionGuide: '해결책을 바로 제시하지 않고 사용자의 표현을 짧게 반영한 뒤 열린 질문을 하나만 한다.', affinity: 2, trust: 4, boundary: 0, nextScene: '자유 대화 · 사용자 이야기', fallback: false },
    { id: 'c-character-story', label: '캐릭터 이야기 듣기', responseType: '캐릭터에게 이야기 요청', condition: '사용자가 말하기보다 캐릭터의 일상을 먼저 듣고 싶어 함', reactionTone: '일상을 가볍게 공유', reactionGuide: '부담이 낮은 일상 이야기를 짧게 들려주고 사용자가 원할 때만 질문한다.', affinity: 1, trust: 2, boundary: 0, nextScene: '자유 대화 · 캐릭터 일상', fallback: false },
    { id: 'c-silence', label: '침묵 또는 짧은 응답', responseType: '대화 진입이 어려움', condition: '침묵이 길거나 한두 단어만 말함', reactionTone: '편안하게 기다림', reactionGuide: '재촉하지 않고 선택지를 두 개만 제시하거나 자신의 이야기를 조금 이어간다.', affinity: 0, trust: 1, boundary: 1, nextScene: '자유 대화 · 낮은 부담', fallback: false },
    { id: 'c-fallback', label: '그 밖의 응답', responseType: '자유 응답', condition: '정해진 진입 유형으로 분류되지 않음', reactionTone: '성격에 맞게 자연스럽게', reactionGuide: '캐릭터 프로필과 최근 대화 맥락을 우선하며 평가나 결말 판정을 하지 않는다.', affinity: 0, trust: 0, boundary: 0, nextScene: '자유 대화 · 계속', fallback: true },
  ],
}

type SceneFlowBranches = Record<Mode, Record<number, FlowBranchDraft[]>>

const createDefaultSceneBranches = (mode: Mode, sceneIndex: number, turnCount: number): FlowBranchDraft[] => {
  const nextScene = sceneIndex + 1 < turnCount ? `장면 ${sceneIndex + 2}` : mode === 'C' ? '자유 대화 · 계속' : '결말 판정'
  const prefix = `${mode.toLowerCase()}-scene-${sceneIndex + 1}`
  return [
    { id: `${prefix}-complete`, label: '장면 목표를 충족함', responseType: '명확한 선택과 이유', condition: '사용자가 이 장면의 행동 목표를 충족하고 필요한 이유나 근거를 함께 말함', reactionTone: '성격에 맞게 자연스럽게', reactionGuide: '캐릭터 성격을 유지하며 사용자의 핵심 표현을 인정하고 다음 장면으로 자연스럽게 연결한다.', affinity: 2, trust: 2, boundary: 0, nextScene, fallback: false },
    { id: `${prefix}-partial`, label: '일부만 답함', responseType: '명확한 선택', condition: '사용자가 장면의 질문에는 답했지만 필요한 이유나 조건 일부를 빠뜨림', reactionTone: '가볍게 재질문', reactionGuide: '이미 답한 부분은 반복해서 요구하지 말고 빠진 정보 한 가지만 짧게 확인한다.', affinity: 0, trust: 1, boundary: 0, nextScene: `장면 ${sceneIndex + 1} · 보충 질문`, fallback: false },
    { id: `${prefix}-avoid`, label: '대답을 피하거나 넘김', responseType: '회피 또는 책임 전가', condition: '사용자가 결정을 미루거나 답변 책임을 캐릭터에게 넘김', reactionTone: '차분하게 맥락 확인', reactionGuide: '비난하지 않고 선택권을 사용자에게 돌려주며 현재 장면의 선택지를 다시 간단히 안내한다.', affinity: -1, trust: -1, boundary: 0, nextScene: `장면 ${sceneIndex + 1} · 다시 시도`, fallback: false },
    { id: `${prefix}-fallback`, label: '그 밖의 응답', responseType: '분류되지 않은 응답', condition: '위 조건과 일치하지 않거나 현재 장면의 맥락이 불명확함', reactionTone: '성격에 맞게 자연스럽게', reactionGuide: '사용자 의도를 임의로 단정하지 말고 현재 상황을 짧게 확인한 뒤 다시 말할 기회를 준다.', affinity: 0, trust: 0, boundary: 0, nextScene: `장면 ${sceneIndex + 1} · 맥락 확인`, fallback: true },
  ]
}

const createInitialSceneFlowBranches = (): SceneFlowBranches => ({
  A: Object.fromEntries(initialDrafts.A.turns.map((_, index) => [index, index === 0 ? initialFlowBranches.A.map((branch) => ({ ...branch })) : createDefaultSceneBranches('A', index, initialDrafts.A.turns.length)])),
  B: Object.fromEntries(initialDrafts.B.turns.map((_, index) => [index, index === 0 ? initialFlowBranches.B.map((branch) => ({ ...branch })) : createDefaultSceneBranches('B', index, initialDrafts.B.turns.length)])),
  C: Object.fromEntries(initialDrafts.C.turns.map((_, index) => [index, index === 0 ? initialFlowBranches.C.map((branch) => ({ ...branch })) : createDefaultSceneBranches('C', index, initialDrafts.C.turns.length)])),
})

const traitOptions = ['다정한', '차분한', '장난스러운', '솔직한', '성숙한', '의젓한', '활발한', '집착기 있는', '무뚝뚝한', '섬세한', '엉뚱한', '수줍은', '보호자 같은', '친구 같은', '츤데레 느낌']
const practiceTypeOptions: Record<Mode, string[]> = {
  A: ['빠르게 결정하기', '이유를 설명하기', '자기 의사 표현하기'],
  B: ['의견 조율하기', '조건 확인하기', '실행 가능한 제안하기'],
  C: ['평가 없는 자유 대화'],
}

function Logo() {
  return <div className="logo-lockup"><span className="logo-symbol">O</span><strong>온기</strong></div>
}

function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={`mode-badge mode-${mode.toLowerCase()}`}>{mode} 모드</span>
}

const characterPortraits: Record<string, string> = { 하루: '/assets/20260811_1726_haru_profile.png' }

function PersonAvatar({ name, accent = 'violet', large = false, image }: { name: string; accent?: string; large?: boolean; image?: string }) {
  const portrait = image || characterPortraits[name]
  return <span className={`person-avatar ${accent} ${large ? 'large' : ''}`} aria-hidden="true">{portrait ? <img src={portrait} alt="" /> : name.slice(0, 1)}</span>
}

function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (page: Page) => void }) {
  const items: { key: Page; icon: string; label: string }[] = [
    { key: 'home', icon: '⌂', label: '홈' },
    { key: 'characters', icon: '◉', label: '캐릭터' },
    { key: 'scenarios', icon: '◇', label: '시나리오' },
    { key: 'builder', icon: '＋', label: '시나리오 제작' },
  ]
  return <aside className="sidebar">
    <Logo />
    <nav>{items.map((item) => <button type="button" key={item.key} className={page === item.key || (item.key === 'characters' && page === 'characterEditor') ? 'active' : ''} onClick={() => onNavigate(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav>
    <div className="sidebar-bottom">
      <div className="voice-policy"><span className="listening-dot" /><div><strong>자동 음성 인식</strong><small>대화 중 항상 대기</small></div></div>
      <button type="button"><span>?</span>도움말</button><button type="button"><span>⚙</span>설정</button>
      <div className="user-chip"><span>가</span><div><strong>가형</strong><small>Creator</small></div></div>
    </div>
  </aside>
}

function TopHeader({ page, onNavigate }: { page: Page; onNavigate: (page: Page) => void }) {
  const names: Partial<Record<Page, string>> = { home: '홈', characters: '캐릭터 관리', scenarios: '시나리오', builder: '시나리오 제작', characterEditor: '캐릭터 설정' }
  return <header className="top-header"><div><span>WORKSPACE</span><strong>{names[page] ?? ''}</strong></div><div className="header-actions"><label className="global-search"><span>⌕</span><input aria-label="통합 검색" placeholder="캐릭터와 시나리오 검색" /></label><button type="button" className="header-icon" aria-label="알림">●<i /></button><button type="button" className="outline-button" onClick={() => onNavigate('builder')}>＋ 새로 만들기</button></div></header>
}

function HomePage({ scenarios, onRun, onNavigate }: { scenarios: Scenario[]; onRun: (scenario: Scenario) => void; onNavigate: (page: Page) => void }) {
  return <div className="page home-page">
    <section className="hero-panel">
      <div><span className="section-eyebrow">CHARACTER VOICE COMPANION</span><h1>연습하고, 상황에 들어가고,<br />편하게 이야기하세요.</h1><p>목적이 다른 세 가지 대화 모드를 웹에서 바로 시작할 수 있습니다.</p><div className="hero-actions"><button type="button" className="primary-button" onClick={() => onRun(scenarios[0])}>A 시나리오 시작</button><button type="button" className="outline-button" onClick={() => onNavigate('builder')}>시나리오 만들기</button></div></div>
      <div className="hero-visual"><div className="visual-card one"><ModeBadge mode="A" /><strong>오늘의 간식 선발전</strong><span>빠르게 선택하고 이유 말하기</span></div><div className="visual-card two"><ModeBadge mode="B" /><strong>오늘 점심은 반드시 정한다</strong><span>여러 의견과 제한 조건 조율하기</span></div><div className="voice-wave"><i /><i /><i /><i /><i /><span>음성 자동 감지 중</span></div></div>
    </section>

    <section className="mode-explainer">
      <article><ModeBadge mode="A" /><h3>가볍게 연습하기</h3><p>한 캐릭터와 짧은 목표를 연습하고, 실제 발화를 근거로 피드백을 받습니다.</p></article>
      <article><ModeBadge mode="B" /><h3>상황 속에서 대화하기</h3><p>여러 캐릭터가 있는 사회적 상황에서 의견과 제한 조건을 조율합니다.</p></article>
      <article><ModeBadge mode="C" /><h3>이야기하기</h3><p>평가 없이 관계를 쌓습니다. 첫 대화가 어려울 때만 점진적 진입을 제공합니다.</p></article>
    </section>

    <section className="content-section">
      <div className="section-title"><div><span className="section-eyebrow">PLAY NOW</span><h2>실제로 플레이할 수 있는 시나리오</h2><p>제작 화면의 예시가 아니라 분기와 결과 화면까지 연결된 시나리오입니다.</p></div><button type="button" className="text-link" onClick={() => onNavigate('scenarios')}>전체 시나리오 →</button></div>
      <div className="scenario-grid">{scenarios.map((scenario) => <ScenarioCard key={scenario.id} scenario={scenario} onRun={() => onRun(scenario)} />)}</div>
    </section>
  </div>
}

function ScenarioCard({ scenario, onRun }: { scenario: Scenario; onRun: () => void }) {
  return <article className={`scenario-card scenario-${scenario.mode.toLowerCase()}`}>
    {scenario.coverImage && <div className="scenario-cover-image"><img src={scenario.coverImage} alt={`${scenario.title} 대표 배경`} /></div>}
    <div className="scenario-card-body"><div className="scenario-card-top"><ModeBadge mode={scenario.mode} /><div className="compact-avatars">{scenario.characterNames.slice(0, 3).map((name, index) => <PersonAvatar key={name} name={name} accent={['violet', 'blue', 'mint'][index]} />)}</div><span>{scenario.duration}</span></div><div className="scenario-meta"><span>{scenario.characterNames.join(' · ')}</span><span>플레이 {scenario.plays}</span></div><h3>{scenario.title}</h3><p>{scenario.summary}</p><button type="button" onClick={onRun}>소개 보기 <span>→</span></button></div>
  </article>
}

function ScenarioLibrary({ scenarios, onRun, onEdit }: { scenarios: Scenario[]; onRun: (scenario: Scenario) => void; onEdit: () => void }) {
  const [filter, setFilter] = useState<'ALL' | Mode>('ALL')
  const visible = filter === 'ALL' ? scenarios : scenarios.filter((scenario) => scenario.mode === filter)
  return <div className="page">
    <div className="page-heading"><div><span className="section-eyebrow">SCENARIO LIBRARY</span><h1>시나리오</h1><p>공개된 A/B/C 시나리오를 시작하거나 내가 만든 시나리오를 수정할 수 있습니다.</p></div><button type="button" className="primary-button" onClick={onEdit}>＋ 시나리오 제작</button></div>
    <div className="filter-tabs"><button className={filter === 'ALL' ? 'active' : ''} onClick={() => setFilter('ALL')}>전체</button>{(['A', 'B', 'C'] as Mode[]).map((mode) => <button key={mode} className={filter === mode ? 'active' : ''} onClick={() => setFilter(mode)}>{mode} 모드</button>)}</div>
    <div className="scenario-grid library-grid">{visible.map((scenario) => <ScenarioCard key={scenario.id} scenario={scenario} onRun={() => onRun(scenario)} />)}</div>
  </div>
}

function CharacterList({ characters, onEdit, onCreate }: { characters: Character[]; onEdit: (character: Character) => void; onCreate: () => void }) {
  return <div className="page">
    <div className="page-heading"><div><span className="section-eyebrow">CHARACTER STUDIO</span><h1>캐릭터 관리</h1><p>A·B·C 모든 모드에서 공통으로 사용할 캐릭터를 만들고 수정합니다.</p></div><button type="button" className="primary-button" onClick={onCreate}>＋ 캐릭터 만들기</button></div>
    <div className="character-stats"><div><strong>{characters.length}</strong><span>내 캐릭터</span></div><div><strong>2</strong><span>공개 캐릭터</span></div><div><strong>6</strong><span>연결된 시나리오</span></div></div>
    <div className="character-grid">{characters.map((character) => <article className="character-card" key={character.id}><div className={`character-cover ${character.accent}`}><PersonAvatar name={character.name} accent={character.accent} image={character.image} large /><span>{character.updated}</span></div><div className="character-card-body"><div><h3>{character.name}</h3><span>{character.relation}</span></div><p>{character.concept}</p><div className="trait-row">{character.traits.map((trait) => <span key={trait}>{trait}</span>)}</div><dl><div><dt>말투</dt><dd>{character.speech}</dd></div><div><dt>목소리</dt><dd>{character.voice}</dd></div></dl><button type="button" className="edit-button" onClick={() => onEdit(character)}>캐릭터 설정 수정</button></div></article>)}</div>
  </div>
}

function Field({ label, required, help, children }: { label: string; required?: boolean; help?: string; children: React.ReactNode }) {
  return <label className="form-field"><span className="form-label">{label}{required && <em>필수</em>}</span>{children}{help && <small>{help}</small>}</label>
}

function CharacterEditor({ character, onCancel, onSave }: { character: Character | null; onCancel: () => void; onSave: (character: Character) => void }) {
  const [form, setForm] = useState<Character>(character ?? { id: `character-${Date.now()}`, name: '', nickname: '', concept: '', persona: '', traits: [], speech: '반말', length: '보통', relation: '편한 친구', voice: '부드럽고 편안한 목소리', accent: 'violet', updated: '방금 수정' })
  const update = <K extends keyof Character>(key: K, value: Character[K]) => setForm((current) => ({ ...current, [key]: value }))
  const toggleTrait = (trait: string) => update('traits', form.traits.includes(trait) ? form.traits.filter((item) => item !== trait) : form.traits.length < 4 ? [...form.traits, trait] : form.traits)
  const valid = form.name.trim() && form.concept.trim().length >= 50 && form.traits.length > 0
  const [activeEditorSection, setActiveEditorSection] = useState(0)
  const editorSections = ['기본 정보', '성격·관계·대화', '목소리와 외형', '추가 설정']
  const moveToEditorSection = (index: number) => {
    setActiveEditorSection(index)
    document.querySelectorAll<HTMLElement>('.editor-form .form-section')[index]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
  useEffect(() => {
    const sections = Array.from(document.querySelectorAll<HTMLElement>('.editor-form .form-section'))
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
      if (visible) setActiveEditorSection(sections.indexOf(visible.target as HTMLElement))
    }, { rootMargin: '-90px 0px -58% 0px', threshold: 0.08 })
    sections.forEach((section) => observer.observe(section))
    return () => observer.disconnect()
  }, [])
  return <div className="page editor-page">
    <div className="editor-titlebar"><button type="button" className="back-button" onClick={onCancel}>←</button><div><span className="section-eyebrow">CHARACTER CUSTOMIZATION</span><h1>{character ? `${character.name} 설정 수정` : '새 캐릭터 만들기'}</h1><p>저장한 설정은 이 캐릭터가 등장하는 A·B·C 모드에 공통 적용됩니다.</p></div><div><button type="button" className="outline-button" onClick={onCancel}>취소</button><button type="button" disabled={!valid} className="primary-button" onClick={() => onSave({ ...form, updated: '방금 수정' })}>설정 저장</button></div></div>
    <div className="editor-layout">
      <aside className="editor-summary"><div className={`character-preview ${form.accent}`}><PersonAvatar name={form.name || '?'} accent={form.accent} image={form.image} large /><strong>{form.name || '이름을 입력하세요'}</strong><span>{form.relation}</span></div><div className="completion-box"><div><strong>설정 완성도</strong><span>{valid ? '100%' : '60%'}</span></div><i><b style={{ width: valid ? '100%' : '60%' }} /></i><p>이름, 콘셉트, 핵심 성격을 입력하면 저장할 수 있습니다.</p></div><nav className="editor-menu" aria-label="캐릭터 설정 목차">{editorSections.map((label, index) => <button type="button" key={label} className={activeEditorSection === index ? 'active' : ''} onClick={() => moveToEditorSection(index)}><span>{String(index + 1).padStart(2, '0')}</span>{label}</button>)}</nav></aside>
      <main className="editor-form">
        <section className="form-section"><div className="form-section-title"><span>01</span><div><h2>기본 정보</h2><p>캐릭터의 이름과 삶을 하나의 명확한 콘셉트로 작성합니다.</p></div></div><div className="two-column"><Field label="이름" required><input value={form.name} onChange={(event) => update('name', event.target.value)} placeholder="예: 루미" /></Field><Field label="별명" help="선택 사항"><input value={form.nickname} onChange={(event) => update('nickname', event.target.value)} placeholder="친해졌을 때 부를 이름" /></Field></div><Field label="캐릭터 콘셉트" required help={`${form.concept.length}/200 · 50~200자`}><textarea rows={5} maxLength={200} value={form.concept} onChange={(event) => update('concept', event.target.value)} placeholder="이 캐릭터는 어디에서 어떤 삶을 살고 있나요?" /></Field><Field label="행동·대화 지침" help="LLM에 전달되는 개별 캐릭터 프롬프트입니다."><textarea rows={5} maxLength={2000} value={form.persona} onChange={(event) => update('persona', event.target.value)} placeholder="어떤 상황에서 어떻게 반응하고, 어떤 표현을 피해야 하는지 작성하세요." /></Field></section>
        <section className="form-section"><div className="form-section-title"><span>02</span><div><h2>성격과 대화</h2><p>서로 모순되지 않도록 핵심 성격은 최대 4개만 선택합니다.</p></div></div><Field label="핵심 성격" required help={`${form.traits.length}/4 선택`}><div className="select-chips">{traitOptions.map((trait) => <button type="button" className={form.traits.includes(trait) ? 'selected' : ''} key={trait} onClick={() => toggleTrait(trait)}>{trait}</button>)}</div></Field><div className="three-column"><Field label="말투"><select value={form.speech} onChange={(event) => update('speech', event.target.value)}><option>반말</option><option>존댓말</option><option>관계에 따라 변화</option></select></Field><Field label="말의 길이"><select value={form.length} onChange={(event) => update('length', event.target.value)}><option>짧게 말함</option><option>보통</option><option>길게 자세히 말함</option></select></Field><Field label="관계 스타일"><select value={form.relation} onChange={(event) => update('relation', event.target.value)}><option>편한 친구</option><option>다정하게 챙겨주는 연상</option><option>장난을 많이 치는 동생</option><option>조용히 곁을 지키는 동료</option><option>차분하게 이끌어주는 선배</option><option>함께 생활하는 룸메이트</option><option>처음 만나 천천히 친해지는 사이</option></select></Field></div></section>
        <section className="form-section"><div className="form-section-title"><span>03</span><div><h2>목소리와 외형</h2><p>목소리는 샘플을 듣고 선택하고, 캐릭터 이미지는 배경과 분리해 등록합니다.</p></div></div><div className="voice-grid">{['밝고 또렷한 목소리', '낮고 차분한 목소리', '부드럽고 편안한 목소리', '졸린 듯 느긋한 목소리'].map((voice) => <button type="button" key={voice} className={form.voice === voice ? 'selected' : ''} onClick={() => update('voice', voice)}><span>▶</span><div><strong>{voice}</strong><small>8초 샘플 듣기</small></div><i>{form.voice === voice ? '선택됨' : ''}</i></button>)}</div><div className="upload-grid"><label className={`upload-panel ${form.image ? 'has-image' : ''}`}><input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) update('image', URL.createObjectURL(file)) }} />{form.image ? <img src={form.image} alt="등록한 캐릭터 미리보기" /> : <span>＋</span>}<strong>{form.image ? '캐릭터 이미지 변경' : '캐릭터 이미지 등록'}</strong><small>배경 없는 PNG 권장 · 최대 10MB</small></label><div className="asset-explanation"><strong>캐릭터와 배경은 별도 자산입니다</strong><p>캐릭터 이미지는 한 번 등록하고 여러 시나리오 배경에 재사용합니다. 장면 미리보기에서 두 레이어를 자동으로 합성하며, 별도 소품 등록은 사용하지 않습니다.</p></div></div></section>
        <section className="form-section"><div className="form-section-title"><span>04</span><div><h2>추가 캐릭터성</h2><p>위 설정으로 표현하기 어려운 습관이나 금지 행동만 간결하게 추가합니다.</p></div></div><Field label="추가 프롬프트" help="선택 사항 · 최대 500자"><textarea rows={4} maxLength={500} placeholder="예: 사용자가 침묵하면 재촉하지 않고 자신의 일상 이야기를 짧게 들려준다." /></Field></section>
      </main>
    </div>
  </div>
}

function ScenarioFlowEditor({ mode, sceneIndex, characterName, branches, branchCounts, selectedId, sceneOptions, turns, onSelectScene, onChange, onRemoveBranch, onRemoveScene, onUpdateTurn, allFlowBranches, onGraphSelect, onGraphChange, onGraphAddBranch, onGraphRemoveBranch }: {
  mode: Mode
  sceneIndex: number
  characterName: string
  branches: FlowBranchDraft[]
  branchCounts: number[]
  selectedId: string
  sceneOptions: string[]
  turns: TurnDraft[]
  onSelectScene: (index: number) => void
  onChange: (id: string, patch: Partial<FlowBranchDraft>) => void
  onRemoveBranch: (id: string) => void
  onRemoveScene: (index: number) => void
  onUpdateTurn: (index: number, patch: Partial<TurnDraft>) => void
  allFlowBranches: Record<number, FlowBranchDraft[]>
  onGraphSelect: (sceneIndex: number, branchId: string) => void
  onGraphChange: (sceneIndex: number, branchId: string, patch: Partial<FlowBranchDraft>) => void
  onGraphAddBranch: (sceneIndex: number) => void
  onGraphRemoveBranch: (sceneIndex: number, branchId: string) => void
}) {
  const [zoom, setZoom] = useState(1)
  const [offset, setOffset] = useState({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState(false)
  const [nodePositions, setNodePositions] = useState<Record<string, { x: number; y: number }>>({})
  const [connectingBranchId, setConnectingBranchId] = useState<string | null>(null)
  const [draggedEdge, setDraggedEdge] = useState<{ sceneIndex: number; branchId: string; x: number; y: number } | null>(null)
  const panRef = useRef({ pointerId: 0, startX: 0, startY: 0, originX: 0, originY: 0 })
  const nodeDragRef = useRef({ pointerId: 0, key: '', startX: 0, startY: 0, originX: 0, originY: 0, width: 0, height: 0 })
  const selected = branches.find((branch) => branch.id === selectedId) ?? branches[0]
  const canvasWidth = Math.max(1320, turns.length * 370 + 260)
  const graphHeight = Math.max(760, Math.max(...turns.map((_, index) => (allFlowBranches[index]?.length ?? 0) * 112 + 230)) + 130)
  const sourceY = graphHeight / 2
  const graphKey = `${mode}-full-flow`
  const positionFor = (key: string, x: number, y: number) => nodePositions[`${graphKey}-${key}`] ?? { x, y }
  const startPosition = positionFor('start', 22, sourceY - 69)
  const classifierPosition = positionFor('classifier', 242, sourceY - 69)
  const scenePositions = turns.map((_, index) => positionFor(`scene-${index}`, 430 + index * 360, sourceY - 69))
  const terminalPosition = positionFor('terminal', 430 + turns.length * 360, sourceY - 49)
  const graphBranchPosition = (currentSceneIndex: number, branch: FlowBranchDraft, branchIndex: number) => positionFor(`graph-${currentSceneIndex}-${branch.id}`, scenePositions[currentSceneIndex].x + 230, 74 + branchIndex * 112)
  const deltaLabel = (value: number) => value > 0 ? `+${value}` : `${value}`
  const connectorPath = (startX: number, startY: number, endX: number, endY: number) => {
    const bend = Math.max(34, Math.abs(endX - startX) * 0.42)
    return `M ${startX} ${startY} C ${startX + bend} ${startY}, ${endX - bend} ${endY}, ${endX} ${endY}`
  }
  const destinationIndex = (nextScene: string) => {
    const match = nextScene.match(/장면\s*(\d+)/)
    if (!match) return -1
    const index = Number(match[1]) - 1
    return index >= 0 && index < turns.length ? index : -1
  }
  const connectToScene = (targetIndex: number, sourceSceneIndex = sceneIndex, sourceBranchId = connectingBranchId) => {
    if (!sourceBranchId) return
    const turn = turns[targetIndex]
    onGraphChange(sourceSceneIndex, sourceBranchId, { nextScene: `장면 ${targetIndex + 1} · ${turn.situation.slice(0, 24)}` })
    setConnectingBranchId(null)
  }
  const requestGraphRemoveBranch = (sourceSceneIndex: number, branch: FlowBranchDraft) => {
    if (window.confirm(`'${branch.label}' 반응 분기를 정말 삭제하시겠습니까?`)) onGraphRemoveBranch(sourceSceneIndex, branch.id)
  }
  const requestRemoveScene = (index: number) => {
    if (turns.length <= 1) return
    if (window.confirm(`장면 ${index + 1}과 연결된 흐름을 정말 삭제하시겠습니까?`)) onRemoveScene(index)
  }
  const changeZoom = (nextZoom: number) => setZoom(Math.min(1.5, Math.max(0.55, Number(nextZoom.toFixed(2)))))
  const resetViewport = () => { setZoom(1); setOffset({ x: 0, y: 0 }) }
  const resetNodeLayout = () => setNodePositions((current) => Object.fromEntries(Object.entries(current).filter(([key]) => !key.startsWith(`${graphKey}-`))))
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest('button, input, textarea, select, label')) return
    panRef.current = { pointerId: event.pointerId, startX: event.clientX, startY: event.clientY, originX: offset.x, originY: offset.y }
    event.currentTarget.setPointerCapture(event.pointerId)
    setIsPanning(true)
  }
  const handlePointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!isPanning || panRef.current.pointerId !== event.pointerId) return
    setOffset({ x: panRef.current.originX + event.clientX - panRef.current.startX, y: panRef.current.originY + event.clientY - panRef.current.startY })
  }
  const handlePointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    setIsPanning(false)
  }
  const handleNodePointerDown = (event: React.PointerEvent<HTMLButtonElement>, key: string, position: { x: number; y: number }, width: number, height: number) => {
    event.stopPropagation()
    nodeDragRef.current = { pointerId: event.pointerId, key: `${graphKey}-${key}`, startX: event.clientX, startY: event.clientY, originX: position.x, originY: position.y, width, height }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const handleNodePointerMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    const drag = nodeDragRef.current
    if (drag.pointerId !== event.pointerId || !drag.key) return
    const x = Math.min(canvasWidth - drag.width, Math.max(0, drag.originX + (event.clientX - drag.startX) / zoom))
    const y = Math.min(graphHeight - drag.height, Math.max(0, drag.originY + (event.clientY - drag.startY) / zoom))
    setNodePositions((current) => ({ ...current, [drag.key]: { x, y } }))
  }
  const handleNodePointerUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    nodeDragRef.current = { pointerId: 0, key: '', startX: 0, startY: 0, originX: 0, originY: 0, width: 0, height: 0 }
  }
  return <section className="builder-block flow-node-builder">
    <div className="block-heading"><div><h2>3. 대화 분기 설계</h2><span>편집할 분기를 선택한 뒤 노드 옆의 ＋ 버튼으로 다음 흐름을 연결합니다.</span></div><div className="flow-heading-actions"><span className="flow-count-chip">장면 {turns.length}개</span><span className="flow-count-chip">현재 분기 {branches.length}개</span></div></div>
    <div className="flow-policy-strip"><span>LLM 역할</span><strong>캐릭터 성격 + 선택된 반응 지침으로 실제 대사를 생성</strong><i /><span>제작자 역할</span><strong>분기 조건·반응 방향·상태 변화·다음 장면 설정</strong></div>
    <div className="flow-control-bar"><span>모든 장면·반응·결말이 같은 캔버스에 표시됩니다. 원형 출력점을 드래그해 다른 장면으로 연결하거나, 빈 공간에 놓아 연결을 해제할 수 있습니다.</span><div><button type="button" className="flow-add-branch-button" onClick={() => onGraphAddBranch(sceneIndex)}>＋ 장면 {sceneIndex + 1} 반응</button><button type="button" aria-label="축소" onClick={() => changeZoom(zoom - 0.1)}>−</button><strong>{Math.round(zoom * 100)}%</strong><button type="button" aria-label="확대" onClick={() => changeZoom(zoom + 0.1)}>＋</button><button type="button" className="reset-view" onClick={resetViewport}>화면 맞춤</button><button type="button" className="reset-view" onClick={resetNodeLayout}>배치 초기화</button></div></div>
    <div className={`flow-canvas-scroll ${isPanning ? 'is-panning' : ''} ${connectingBranchId ? 'is-connecting' : ''}`} onPointerDown={handlePointerDown} onPointerMove={handlePointerMove} onPointerUp={handlePointerUp} onPointerCancel={handlePointerUp} onWheel={(event) => { event.preventDefault(); changeZoom(zoom + (event.deltaY < 0 ? 0.08 : -0.08)) }}><div className={`flow-canvas mode-flow-${mode.toLowerCase()}`} style={{ width: canvasWidth, minWidth: canvasWidth, height: graphHeight, transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}>
      <svg className="flow-connectors" viewBox={`0 0 ${canvasWidth} ${graphHeight}`} preserveAspectRatio="none" aria-hidden="true">
        <path className="flow-line main-line" d={connectorPath(startPosition.x + 182, startPosition.y + 69, classifierPosition.x, classifierPosition.y + 69)} />
        <path className="flow-line main-line" d={connectorPath(classifierPosition.x + 190, classifierPosition.y + 69, scenePositions[0].x, scenePositions[0].y + 69)} />
        {turns.slice(0, -1).map((_, index) => <path key={`scene-link-${index}`} className="flow-line main-line" d={connectorPath(scenePositions[index].x + 182, scenePositions[index].y + 69, scenePositions[index + 1].x, scenePositions[index + 1].y + 69)} />)}
        {turns.map((_, currentSceneIndex) => (allFlowBranches[currentSceneIndex] ?? []).map((branch, branchIndex) => {
          const branchPosition = graphBranchPosition(currentSceneIndex, branch, branchIndex)
          const targetIndex = destinationIndex(branch.nextScene)
          const target = targetIndex >= 0 ? scenePositions[targetIndex] : terminalPosition
          const dragging = draggedEdge?.branchId === branch.id && draggedEdge.sceneIndex === currentSceneIndex
          return <g key={`edge-${currentSceneIndex}-${branch.id}`}><path className={`flow-line branch-line ${currentSceneIndex === sceneIndex && branch.id === selected?.id ? 'selected' : ''}`} d={connectorPath(scenePositions[currentSceneIndex].x + 182, scenePositions[currentSceneIndex].y + 69, branchPosition.x, branchPosition.y + 45)} />{branch.nextScene && <path className="flow-line merge-line" d={connectorPath(branchPosition.x + 232, branchPosition.y + 45, dragging ? draggedEdge.x : target.x, dragging ? draggedEdge.y : target.y + 49)} />}</g>
        }))}
      </svg>
      <button type="button" className="flow-node scene-node start-node" style={{ left: startPosition.x, top: startPosition.y }} onPointerDown={(event) => handleNodePointerDown(event, 'start', startPosition, 182, 138)} onPointerMove={handleNodePointerMove} onPointerUp={handleNodePointerUp} onPointerCancel={handleNodePointerUp}><span>시작</span><strong>{characterName}가 대화를 시작</strong><small>첫 사용자 발화 분석으로 연결</small><i>▶</i></button>
      <button type="button" className="flow-node classifier-node" style={{ left: classifierPosition.x, top: classifierPosition.y }} onPointerDown={(event) => handleNodePointerDown(event, 'classifier', classifierPosition, 190, 138)} onPointerMove={handleNodePointerMove} onPointerUp={handleNodePointerUp} onPointerCancel={handleNodePointerUp}><span>사용자 발화 분석</span><strong>의도·이유·맥락 분류</strong><small>LLM이 현재 장면의 반응 조건을 선택</small><i>AI</i></button>
      {turns.map((turn, index) => <div key={`scene-${index}`}><button type="button" className={`flow-node scene-node destination-scene-node ${sceneIndex === index ? 'selected' : ''}`} style={{ left: scenePositions[index].x, top: scenePositions[index].y }} onPointerDown={(event) => handleNodePointerDown(event, `scene-${index}`, scenePositions[index], 182, 138)} onPointerMove={handleNodePointerMove} onPointerUp={handleNodePointerUp} onPointerCancel={handleNodePointerUp} onClick={() => onSelectScene(index)}><span>장면 {index + 1}</span><strong>{turn.situation}</strong><small>{turn.background} · 클릭하여 해당 장면 편집</small><i>{index + 1}</i></button>{turns.length > 1 && <button type="button" className="node-delete-button" style={{ left: scenePositions[index].x + 126, top: scenePositions[index].y + 7 }} onClick={() => requestRemoveScene(index)}>삭제</button>}<button type="button" className="scene-add-branch" style={{ left: scenePositions[index].x + 22, top: scenePositions[index].y + 148 }} onClick={() => onGraphAddBranch(index)}>＋ 반응 추가</button></div>)}
      {turns.map((_, currentSceneIndex) => (allFlowBranches[currentSceneIndex] ?? []).map((branch, branchIndex) => { const position = graphBranchPosition(currentSceneIndex, branch, branchIndex); return <div key={`branch-${currentSceneIndex}-${branch.id}`}><button type="button" className={`flow-node branch-node ${currentSceneIndex === sceneIndex && branch.id === selectedId ? 'selected' : ''} ${branch.fallback ? 'fallback' : ''}`} style={{ left: position.x, top: position.y }} onPointerDown={(event) => handleNodePointerDown(event, `graph-${currentSceneIndex}-${branch.id}`, position, 232, 90)} onPointerMove={handleNodePointerMove} onPointerUp={handleNodePointerUp} onPointerCancel={handleNodePointerUp} onClick={() => onGraphSelect(currentSceneIndex, branch.id)}><span>{branch.fallback ? '기본 반응' : '반응 조건'}</span><strong>{branch.label}</strong><small>{branch.reactionTone}</small><div><b className={branch.affinity >= 0 ? 'positive' : 'negative'}>호감 {deltaLabel(branch.affinity)}</b><b className={branch.trust >= 0 ? 'positive' : 'negative'}>신뢰 {deltaLabel(branch.trust)}</b></div></button><button type="button" className="node-delete-button" style={{ left: position.x + 176, top: position.y + 7 }} onClick={() => requestGraphRemoveBranch(currentSceneIndex, branch)}>삭제</button><button type="button" className="flow-port branch-output-port" style={{ left: position.x + 222, top: position.y + 36 }} onPointerDown={(event) => { event.stopPropagation(); event.currentTarget.setPointerCapture(event.pointerId); onGraphSelect(currentSceneIndex, branch.id); setConnectingBranchId(branch.id); setDraggedEdge({ sceneIndex: currentSceneIndex, branchId: branch.id, x: position.x + 232, y: position.y + 45 }) }} onPointerMove={(event) => { if (draggedEdge?.branchId !== branch.id || draggedEdge.sceneIndex !== currentSceneIndex) return; const bounds = event.currentTarget.closest('.flow-canvas')?.getBoundingClientRect(); if (!bounds) return; setDraggedEdge({ sceneIndex: currentSceneIndex, branchId: branch.id, x: (event.clientX - bounds.left) / zoom, y: (event.clientY - bounds.top) / zoom }) }} onPointerUp={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); if (!draggedEdge) return; const target = turns.map((_, targetIndex) => scenePositions[targetIndex]).findIndex((target) => Math.hypot(target.x - draggedEdge.x, target.y + 69 - draggedEdge.y) < 100); if (target >= 0) connectToScene(target, currentSceneIndex, branch.id); else onGraphChange(currentSceneIndex, branch.id, { nextScene: '' }); setDraggedEdge(null); setConnectingBranchId(null) }} aria-label={`${branch.label} 연결 드래그`} /></div> }))}
      {turns.some((_, index) => (allFlowBranches[index] ?? []).some((branch) => branch.nextScene && destinationIndex(branch.nextScene) < 0)) && <button type="button" className="flow-node terminal-node" style={{ left: terminalPosition.x, top: terminalPosition.y }} onPointerDown={(event) => handleNodePointerDown(event, 'terminal', terminalPosition, 210, 98)} onPointerMove={handleNodePointerMove} onPointerUp={handleNodePointerUp} onPointerCancel={handleNodePointerUp}><span>{mode === 'C' ? '자유 대화' : '결말'}</span><strong>{mode === 'C' ? '자유 대화 계속' : '등록한 결말 조건 판정'}</strong><small>여러 반응이 같은 결말로 연결될 수 있습니다.</small><i>✓</i></button>}
    </div></div>
    {selected && <div className="flow-detail-layout"><section className="flow-detail-panel"><header><div><span>선택한 분기 설정</span><h3>{selected.label}</h3></div>{!selected.fallback && branches.length > 2 && <button type="button" onClick={() => onRemoveBranch(selected.id)}>분기 삭제</button>}</header><div className="flow-detail-grid"><Field label="분기 이름"><input value={selected.label} onChange={(event) => onChange(selected.id, { label: event.target.value })} /></Field><Field label="사용자 응답 유형"><select value={selected.responseType} onChange={(event) => onChange(selected.id, { responseType: event.target.value })}><option>명확한 선택과 이유</option><option>명확한 선택</option><option>회피 또는 책임 전가</option><option>상대에게 질문</option><option>감정 또는 일상 공유</option><option>침묵 또는 짧은 응답</option><option>분류되지 않은 응답</option></select></Field><Field label="분기 조건" required help="실제 문장 예시가 아니라 의미와 행동 기준을 작성합니다."><textarea rows={3} value={selected.condition} onChange={(event) => onChange(selected.id, { condition: event.target.value })} /></Field><div className="reaction-setting"><Field label="캐릭터 반응 톤"><select value={selected.reactionTone} onChange={(event) => onChange(selected.id, { reactionTone: event.target.value })}><option>장난스럽게 인정</option><option>가볍게 재질문</option><option>장난스럽지만 단호하게</option><option>차분하게 맥락 확인</option><option>서두르지 않고 경청</option><option>성격에 맞게 자연스럽게</option></select></Field><Field label="다음 장면"><select value={selected.nextScene} onChange={(event) => { onChange(selected.id, { nextScene: event.target.value }); setConnectingBranchId(null) }}><option value="">연결 안 됨</option>{sceneOptions.map((scene) => <option key={scene}>{scene}</option>)}{selected.nextScene && !sceneOptions.includes(selected.nextScene) && <option>{selected.nextScene}</option>}</select></Field></div><Field label="LLM 반응 지침" required help="실제 대사는 캐릭터 프로필과 이 지침을 조합해 생성합니다."><textarea rows={4} value={selected.reactionGuide} onChange={(event) => onChange(selected.id, { reactionGuide: event.target.value })} /></Field></div></section><aside className="state-change-panel"><span>내부 관계 상태 변화</span><p>결말과 다음 반응 계산에는 사용하지만 플레이 화면에 숫자로 노출하지 않습니다.</p><label><span>호감도</span><input type="number" min="-10" max="10" value={selected.affinity} onChange={(event) => onChange(selected.id, { affinity: Number(event.target.value) })} /></label><label><span>신뢰도</span><input type="number" min="-10" max="10" value={selected.trust} onChange={(event) => onChange(selected.id, { trust: Number(event.target.value) })} /></label><label><span>경계 완화</span><input type="number" min="-10" max="10" value={selected.boundary} onChange={(event) => onChange(selected.id, { boundary: Number(event.target.value) })} /></label><div className="state-preview"><strong>이 분기가 실행되면</strong><span>호감 {deltaLabel(selected.affinity)} · 신뢰 {deltaLabel(selected.trust)} · 경계 {deltaLabel(selected.boundary)}</span></div></aside></div>}
    <details className="flow-scene-library" open><summary><span><strong>장면 내용과 배경 편집</strong><small>총 {turns.length}개 · 각 장면 안에서 상황, 대사, 사용자 행동, 배경을 함께 설정합니다.</small></span><b>펼쳐보기</b></summary><div className="flow-scene-list">{turns.map((turn, index) => <article className={sceneIndex === index ? 'active' : ''} key={`flow-scene-${index}`}><header><button type="button" className="scene-select-button" onClick={() => onSelectScene(index)}><span>{index + 1}</span><div><strong>장면 {index + 1}</strong><small>{branchCounts[index] ?? 0}개 반응 분기</small></div></button></header><Field label="배경 이름"><input value={turn.background} onChange={(event) => onUpdateTurn(index, { background: event.target.value })} /></Field><label className={`scene-background-upload ${turn.backgroundImage ? 'has-image' : ''}`}><input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) onUpdateTurn(index, { backgroundImage: URL.createObjectURL(file) }) }} />{turn.backgroundImage ? <img src={turn.backgroundImage} alt={`장면 ${index + 1} 배경 미리보기`} /> : <span>＋</span>}<div><strong>{turn.backgroundImage ? '장면 배경 변경' : '장면 배경 업로드'}</strong><small>사진은 장면 비율에 맞게 잘라 표시하며 늘려서 찌그러뜨리지 않습니다.</small></div></label><Field label="화면 상황 설명"><input value={turn.situation} onChange={(event) => onUpdateTurn(index, { situation: event.target.value })} /></Field><Field label="캐릭터 시작 대사"><textarea rows={3} value={turn.line} onChange={(event) => onUpdateTurn(index, { line: event.target.value })} /></Field><Field label="사용자가 해야 하는 행동"><input value={turn.userGoal} onChange={(event) => onUpdateTurn(index, { userGoal: event.target.value })} /></Field></article>)}</div></details>
    <div className="flow-legend"><span><i className="legend-scene" />장면</span><span><i className="legend-ai" />LLM 분류</span><span><i className="legend-branch" />진한 테두리는 현재 편집 중인 분기</span><span><i className="legend-fallback" />일치하지 않을 때 기본 경로</span></div>
  </section>
}

function ScenarioBuilder({ onBack, onSaved }: { onBack: () => void; onSaved: () => void }) {
  const [mode, setMode] = useState<Mode>('A')
  const [section, setSection] = useState<BuilderSection>('overview')
  const [drafts, setDrafts] = useState(initialDrafts)
  const [characterSources, setCharacterSources] = useState<Record<Mode, 'new' | 'existing'>>({ A: 'new', B: 'new', C: 'new' })
  const [scenarioCharacters, setScenarioCharacters] = useState<Record<Mode, ScenarioCharacterDraft[]>>({
    A: [{ ...initialCharacters[0], traits: [...initialCharacters[0].traits] }],
    B: [{ ...initialCharacters[2], traits: [...initialCharacters[2].traits] }],
    C: [{ ...initialCharacters[1], traits: [...initialCharacters[1].traits] }],
  })
  const [leadCharacterIds, setLeadCharacterIds] = useState<Record<Mode, string>>({ A: 'haru', B: 'jiyoon', C: 'lumi' })
  const [flowBranches, setFlowBranches] = useState<SceneFlowBranches>(createInitialSceneFlowBranches)
  const [selectedFlowSceneIndexes, setSelectedFlowSceneIndexes] = useState<Record<Mode, number>>({ A: 0, B: 0, C: 0 })
  const [selectedFlowBranchIds, setSelectedFlowBranchIds] = useState<Record<Mode, string>>({ A: initialFlowBranches.A[0].id, B: initialFlowBranches.B[0].id, C: initialFlowBranches.C[0].id })
  const draft = drafts[mode]
  const activeCharacters = scenarioCharacters[mode]
  const activeFlowSceneIndex = selectedFlowSceneIndexes[mode]
  const activeFlowBranches = flowBranches[mode][activeFlowSceneIndex] ?? []
  const updateDraft = (patch: Partial<ScenarioDraft>) => setDrafts((current) => ({ ...current, [mode]: { ...current[mode], ...patch } }))
  const updateTurn = (index: number, patch: Partial<TurnDraft>) => updateDraft({ turns: draft.turns.map((turn, turnIndex) => turnIndex === index ? { ...turn, ...patch } : turn) })
  const updateEnding = (index: number, patch: Partial<EndingDraft>) => updateDraft({ endings: draft.endings.map((ending, endingIndex) => endingIndex === index ? { ...ending, ...patch } : ending) })
  const commitCharacters = (nextCharacters: ScenarioCharacterDraft[]) => {
    setScenarioCharacters((current) => ({ ...current, [mode]: nextCharacters }))
    updateDraft({ characters: nextCharacters.map((character) => character.name).filter(Boolean).join(' · ') })
  }
  const updateScenarioCharacter = (index: number, patch: Partial<ScenarioCharacterDraft>) => commitCharacters(activeCharacters.map((character, characterIndex) => characterIndex === index ? { ...character, ...patch } : character))
  const importCharacter = (characterId: string) => {
    const selected = initialCharacters.find((character) => character.id === characterId)
    if (!selected) return
    const imported: ScenarioCharacterDraft = { ...selected, traits: [...selected.traits] }
    if (mode !== 'C') {
      commitCharacters([imported])
      setLeadCharacterIds((current) => ({ ...current, [mode]: imported.id }))
      return
    }
    const alreadySelected = activeCharacters.some((character) => character.id === characterId)
    if (alreadySelected) {
      if (activeCharacters.length <= 1) return
      const nextCharacters = activeCharacters.filter((character) => character.id !== characterId)
      commitCharacters(nextCharacters)
      if (leadCharacterIds.C === characterId) setLeadCharacterIds((current) => ({ ...current, C: nextCharacters[0].id }))
      return
    }
    if (activeCharacters.length < 3) commitCharacters([...activeCharacters, imported])
  }
  const addCCharacter = () => {
    if (activeCharacters.length >= 3) return
    const index = activeCharacters.length + 1
    commitCharacters([...activeCharacters, { id: `scenario-character-${Date.now()}`, name: `캐릭터 ${index}`, concept: '', traits: [], speech: '관계에 따라 변화', relation: '처음 만나 천천히 친해지는 사이', voice: '부드럽고 편안한 목소리' }])
  }
  const removeCCharacter = (index: number) => {
    if (activeCharacters.length <= 1) return
    const removed = activeCharacters[index]
    const nextCharacters = activeCharacters.filter((_, characterIndex) => characterIndex !== index)
    commitCharacters(nextCharacters)
    if (leadCharacterIds.C === removed.id) setLeadCharacterIds((current) => ({ ...current, C: nextCharacters[0].id }))
  }
  const selectFlowScene = (sceneIndex: number) => {
    const nextBranches = flowBranches[mode][sceneIndex] ?? []
    setSelectedFlowSceneIndexes((current) => ({ ...current, [mode]: sceneIndex }))
    setSelectedFlowBranchIds((current) => ({ ...current, [mode]: nextBranches[0]?.id ?? '' }))
  }
  const updateFlowBranch = (branchId: string, patch: Partial<FlowBranchDraft>) => setFlowBranches((current) => ({ ...current, [mode]: { ...current[mode], [activeFlowSceneIndex]: current[mode][activeFlowSceneIndex].map((branch) => branch.id === branchId ? { ...branch, ...patch } : branch) } }))
  const removeFlowBranch = (branchId: string) => {
    const target = activeFlowBranches.find((branch) => branch.id === branchId)
    if (target && !window.confirm(`'${target.label}' 반응 분기를 정말 삭제하시겠습니까?`)) return
    const nextBranches = activeFlowBranches.filter((branch) => branch.id !== branchId)
    setFlowBranches((current) => ({ ...current, [mode]: { ...current[mode], [activeFlowSceneIndex]: nextBranches } }))
    setSelectedFlowBranchIds((current) => ({ ...current, [mode]: nextBranches[0]?.id ?? '' }))
  }
  const removeFlowScene = (sceneIndex: number) => {
    if (draft.turns.length <= 1) return
    const nextTurns = draft.turns.filter((_, index) => index !== sceneIndex)
    updateDraft({ turns: nextTurns })
    setFlowBranches((current) => {
      const nextMode = Object.fromEntries(Object.entries(current[mode]).filter(([index]) => Number(index) !== sceneIndex).map(([index, branches]) => [Number(index) > sceneIndex ? Number(index) - 1 : Number(index), branches]))
      return { ...current, [mode]: nextMode }
    })
    setSelectedFlowSceneIndexes((current) => ({ ...current, [mode]: Math.max(0, Math.min(activeFlowSceneIndex, nextTurns.length - 1)) }))
  }
  const sections: { key: BuilderSection; icon: string; label: string }[] = [
    { key: 'overview', icon: '▤', label: '개요' }, { key: 'characters', icon: '◉', label: '캐릭터 설정' }, { key: 'flow', icon: '◇', label: '대화 흐름' }, { key: 'endings', icon: '⚑', label: '결말 설정' },
    { key: 'rules', icon: '⚙', label: '설정·규칙' }, { key: 'preview', icon: '▷', label: '미리보기' },
  ]
  return <div className="builder-page">
    <header className="builder-top"><button type="button" className="back-button" onClick={onBack}>←</button><strong>시나리오 제작</strong><div className="mode-tabs">{(['A', 'B', 'C'] as Mode[]).map((item) => <button type="button" key={item} className={mode === item ? 'active' : ''} onClick={() => { setMode(item); setSection('overview') }}>{item} 모드</button>)}</div><div className="builder-actions"><button type="button" className="outline-button" onClick={() => setSection('preview')}>▷ 미리보기</button><button type="button" className="outline-button" onClick={onSaved}>저장</button><button type="button" className="primary-button" onClick={onSaved}>게시하기</button></div></header>
    <div className="builder-workspace">
      <aside className="builder-side"><nav>{sections.map((item) => <button type="button" key={item.key} disabled={mode === 'C' && item.key === 'endings'} className={section === item.key ? 'active' : ''} onClick={() => setSection(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="guide-card"><span>☼</span><strong>제작 가이드</strong><p>{mode === 'C' ? 'C 모드는 하나의 시작 장면과 대표 화자를 정합니다. 다른 캐릭터는 동시에 소개하지 않고 대화 흐름에 맞춰 참여합니다.' : 'A·B 모드는 주 캐릭터 한 명과 장면별 사용자 참여 목표를 반드시 설정합니다.'}</p><button type="button">가이드 보기</button></div></aside>
      <main className="builder-main">
        {section === 'overview' && <section className="builder-block"><div className="block-heading"><div><h2>1. 시나리오 개요</h2><span>플레이를 시작하기 전에 사용자에게 보여줄 정보와 대표 배경입니다.</span></div><span>{mode === 'C' ? '평가 없는 자유 대화' : `${mode} 모드 시나리오`}</span></div><div className="builder-form-grid"><Field label="시나리오 제목" required><input value={draft.title} onChange={(event) => updateDraft({ title: event.target.value })} /></Field><Field label="한 줄 설명" required><input value={draft.summary} onChange={(event) => updateDraft({ summary: event.target.value })} /></Field><Field label="시작 전 안내" required help="사용자가 무엇을 하게 되는지 알려주되 결말 조건은 공개하지 않습니다."><textarea rows={4} value={draft.openingGuide} onChange={(event) => updateDraft({ openingGuide: event.target.value })} /></Field><div className="overview-side-fields"><Field label="예상 소요 시간"><input value={draft.estimatedDuration} onChange={(event) => updateDraft({ estimatedDuration: event.target.value })} /></Field><Field label={mode === 'A' ? '연습 유형' : mode === 'B' ? '상황 유형' : '대화 유형'} help={mode === 'C' ? 'C 모드는 평가 없는 자유 대화로 고정됩니다.' : undefined}><select value={draft.practiceType} disabled={mode === 'C'} onChange={(event) => updateDraft({ practiceType: event.target.value })}>{practiceTypeOptions[mode].map((option) => <option key={option}>{option}</option>)}</select></Field></div><div className="scenario-cover-setting"><div className="scenario-cover-copy"><Field label="대표 배경 이름" required><input value={draft.background} onChange={(event) => updateDraft({ background: event.target.value })} /></Field><strong>시나리오 대표 배경</strong><p>메인 카드와 시작 전 소개에 표시됩니다. 장면별 배경은 대화 흐름의 각 장면에서 따로 바꿀 수 있습니다.</p></div><label className={`scenario-cover-upload ${draft.coverImage ? 'has-image' : ''}`}><input type="file" accept="image/*" onChange={(event) => { const file = event.target.files?.[0]; if (file) updateDraft({ coverImage: URL.createObjectURL(file) }) }} />{draft.coverImage ? <img src={draft.coverImage} alt="시나리오 대표 배경 미리보기" /> : <span>＋</span>}<div><strong>{draft.coverImage ? '대표 배경 변경' : '대표 배경 업로드'}</strong><small>가로 이미지 권장 · 원본 비율을 유지해 잘라 표시</small></div></label></div>{mode !== 'C' && <label className="toggle-field"><span><strong>관계 변화 사용</strong><small>대화 피드백과 별도로 캐릭터의 마지막 반응에 반영합니다.</small></span><button type="button" className={draft.useAffinity ? 'toggle active' : 'toggle'} onClick={() => updateDraft({ useAffinity: !draft.useAffinity })}><i /></button></label>}</div><div className="builder-note"><strong>결말 정보 공개 기준</strong><p>사용자는 시작 전에 결말의 총개수만 볼 수 있습니다. 이름, 달성 조건, 공략 힌트는 플레이 전후 모두 잠금 상태로 유지합니다.</p></div></section>}
        {section === 'characters' && <section className="builder-block character-builder"><div className="block-heading"><div><h2>2. 캐릭터 설정</h2><span>{mode === 'C' ? '1~3명 · 대표 화자 1명' : '주 캐릭터 정확히 1명'}</span></div>{mode === 'C' && <button type="button" className="soft-button" onClick={addCCharacter} disabled={activeCharacters.length >= 3}>＋ 캐릭터 추가</button>}</div><div className="character-source-tabs"><button type="button" className={characterSources[mode] === 'new' ? 'active' : ''} onClick={() => setCharacterSources((current) => ({ ...current, [mode]: 'new' }))}>시나리오 안에서 새로 만들기</button><button type="button" className={characterSources[mode] === 'existing' ? 'active' : ''} onClick={() => setCharacterSources((current) => ({ ...current, [mode]: 'existing' }))}>기존 캐릭터 불러오기</button></div>{characterSources[mode] === 'existing' && <div className="existing-character-picker"><label><span>캐릭터 라이브러리</span><select value={activeCharacters[0]?.id ?? ''} onChange={(event) => importCharacter(event.target.value)}>{initialCharacters.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.relation}</option>)}</select></label><p>불러온 설정은 이 시나리오 안에서 수정해도 원본 캐릭터에는 영향을 주지 않습니다.</p></div>}<div className="scenario-character-list">{activeCharacters.map((character, index) => <article className="scenario-character-config" key={character.id}><header><div><PersonAvatar name={character.name || '?'} accent={['violet', 'blue', 'mint'][index]} /><span><strong>{character.name || `캐릭터 ${index + 1}`}</strong><small>{mode === 'C' && leadCharacterIds.C === character.id ? '공통 시작 장면의 대표 화자' : mode === 'C' ? '대화 중 순차 참여' : '주 캐릭터'}</small></span></div><div>{mode === 'C' && <label className="lead-speaker-radio"><input type="radio" name="lead-character" checked={leadCharacterIds.C === character.id} onChange={() => setLeadCharacterIds((current) => ({ ...current, C: character.id }))} /> 대표 화자</label>}{mode === 'C' && activeCharacters.length > 1 && <button type="button" className="remove-character" onClick={() => removeCCharacter(index)}>삭제</button>}</div></header><div className="character-config-grid"><Field label="이름" required><input value={character.name} onChange={(event) => updateScenarioCharacter(index, { name: event.target.value })} /></Field><Field label="관계 스타일"><select value={character.relation} onChange={(event) => updateScenarioCharacter(index, { relation: event.target.value })}><option>처음 만나 천천히 친해지는 사이</option><option>편한 친구</option><option>조용히 곁을 지키는 동료</option><option>차분하게 이끌어주는 선배</option><option>함께 생활하는 룸메이트</option></select></Field><Field label="캐릭터 성격과 상황" required help="C 모드는 성격만 설정해도 시작할 수 있습니다."><textarea rows={4} value={character.concept} onChange={(event) => updateScenarioCharacter(index, { concept: event.target.value })} placeholder="성격, 관심사, 사용자와의 현재 관계를 작성하세요." /></Field><div className="character-voice-fields"><Field label="말투"><select value={character.speech} onChange={(event) => updateScenarioCharacter(index, { speech: event.target.value })}><option>반말</option><option>존댓말</option><option>관계에 따라 변화</option></select></Field><Field label="목소리"><select value={character.voice} onChange={(event) => updateScenarioCharacter(index, { voice: event.target.value })}><option>밝고 또렷한 목소리</option><option>낮고 차분한 목소리</option><option>부드럽고 편안한 목소리</option><option>졸린 듯 느긋한 목소리</option></select></Field></div></div><Field label="핵심 성격" help={`${character.traits.length}/4 선택`}><div className="select-chips compact">{traitOptions.map((trait) => <button type="button" key={trait} className={character.traits.includes(trait) ? 'selected' : ''} onClick={() => updateScenarioCharacter(index, { traits: character.traits.includes(trait) ? character.traits.filter((item) => item !== trait) : character.traits.length < 4 ? [...character.traits, trait] : character.traits })}>{trait}</button>)}</div></Field></article>)}</div>{mode === 'C' && <div className="builder-note c-opening-rule"><strong>C 모드의 시작 장면 규칙</strong><p>캐릭터마다 별도 시작 시나리오를 동시에 실행하지 않습니다. 하나의 공통 시작 장면에서 대표 화자 한 명만 먼저 대화를 시작하고, 나머지 캐릭터는 장면 디렉터가 대화 맥락에 맞춰 순차적으로 참여시킵니다.</p></div>}<div className="builder-note"><strong>저장 방식</strong><p>캐릭터 설정은 이 시나리오와 함께 저장됩니다. 완성 후 원하면 캐릭터 라이브러리에 재사용 가능한 템플릿으로 별도 저장할 수 있습니다.</p></div></section>}
        {section === 'flow' && <ScenarioFlowEditor mode={mode} sceneIndex={activeFlowSceneIndex} characterName={mode === 'C' ? activeCharacters.find((character) => character.id === leadCharacterIds.C)?.name ?? activeCharacters[0]?.name ?? '캐릭터' : activeCharacters[0]?.name ?? '캐릭터'} branches={activeFlowBranches} branchCounts={draft.turns.map((_, index) => flowBranches[mode][index]?.length ?? 0)} selectedId={selectedFlowBranchIds[mode]} sceneOptions={draft.turns.map((turn, index) => `장면 ${index + 1} · ${turn.situation.slice(0, 24)}`)} turns={draft.turns} onSelectScene={selectFlowScene} onChange={updateFlowBranch} onRemoveBranch={removeFlowBranch} onRemoveScene={removeFlowScene} onUpdateTurn={updateTurn} allFlowBranches={flowBranches[mode]} onGraphSelect={(targetSceneIndex, id) => { setSelectedFlowSceneIndexes((current) => ({ ...current, [mode]: targetSceneIndex })); setSelectedFlowBranchIds((current) => ({ ...current, [mode]: id })) }} onGraphChange={(targetSceneIndex, id, patch) => setFlowBranches((current) => ({ ...current, [mode]: { ...current[mode], [targetSceneIndex]: current[mode][targetSceneIndex].map((branch) => branch.id === id ? { ...branch, ...patch } : branch) } }))} onGraphAddBranch={(targetSceneIndex) => { const existing = flowBranches[mode][targetSceneIndex] ?? []; if (existing.length >= 6) return; const id = `${mode.toLowerCase()}-scene-${targetSceneIndex + 1}-branch-${Date.now()}`; const branch: FlowBranchDraft = { id, label: '새 반응 분기', responseType: '명확한 선택', condition: '이 분기로 보낼 사용자 발화의 의미와 행동 조건을 작성하세요.', reactionTone: '성격에 맞게 자연스럽게', reactionGuide: '캐릭터 성격을 유지하면서 사용자의 핵심 의도에 반응하고 다음 장면으로 자연스럽게 연결한다.', affinity: 0, trust: 0, boundary: 0, nextScene: draft.turns[targetSceneIndex + 1] ? `장면 ${targetSceneIndex + 2}` : mode === 'C' ? '자유 대화 · 계속' : '결말 판정', fallback: false }; setFlowBranches((current) => ({ ...current, [mode]: { ...current[mode], [targetSceneIndex]: [...existing.filter((item) => !item.fallback), branch, ...existing.filter((item) => item.fallback)] } })); setSelectedFlowSceneIndexes((current) => ({ ...current, [mode]: targetSceneIndex })); setSelectedFlowBranchIds((current) => ({ ...current, [mode]: id })) }} onGraphRemoveBranch={(targetSceneIndex, id) => { const next = (flowBranches[mode][targetSceneIndex] ?? []).filter((branch) => branch.id !== id); setFlowBranches((current) => ({ ...current, [mode]: { ...current[mode], [targetSceneIndex]: next } })); if (targetSceneIndex === activeFlowSceneIndex) setSelectedFlowBranchIds((current) => ({ ...current, [mode]: next[0]?.id ?? '' })) }} />}
        {section === 'endings' && mode !== 'C' && <section className="builder-block ending-builder"><div className="block-heading"><div><h2>결말 설정</h2><span>점수가 아니라 행동 기록·관계 변화·서사 분기로 판정합니다.</span></div><button className="soft-button" onClick={() => updateDraft({ endings: [...draft.endings, { name: '새 결말', description: '사용자에게 보여줄 서사적 결과를 작성하세요.', condition: '어떤 플레이에서 나오는 결말인지 자연어로 작성하세요.' }] })}>＋ 결말 추가</button></div><div className="ending-grid">{draft.endings.map((ending, index) => <article className="ending-edit-card" key={`${mode}-ending-${index}`}><div><span>{index + 1}</span><button type="button">•••</button></div><Field label="결말 이름"><input value={ending.name} onChange={(event) => updateEnding(index, { name: event.target.value })} /></Field><Field label="결말 설명"><textarea rows={4} value={ending.description} onChange={(event) => updateEnding(index, { description: event.target.value })} /></Field><Field label="어떤 플레이에서 나오는 결말인지"><textarea rows={3} value={ending.condition} onChange={(event) => updateEnding(index, { condition: event.target.value })} /></Field><small>AI가 사용자 발화와 행동 기록을 분석해 세부 조건을 생성합니다.</small></article>)}</div></section>}
        {section === 'rules' && <section className="builder-block"><div className="block-heading"><div><h2>AI 자동 생성 규칙</h2><span>제작자가 모든 사용자 답변 분기를 직접 작성하지 않아도 됩니다.</span></div><button className="soft-button">자동 생성 다시 실행</button></div><div className="rule-layout"><article><h3>사용자 응답 유형</h3>{['명확한 선택 + 이유 설명', '명확한 선택', '결정을 미룸 / 회피', '캐릭터에게 질문함', '농담이나 엉뚱한 응답', '맥락과 맞지 않는 응답'].map((item, index) => <div className={`rule-line level-${index < 2 ? 'good' : index < 4 ? 'mid' : 'warn'}`} key={item}><i />{item}<span>{index < 2 ? '적합' : index < 4 ? '확인' : '주의'}</span></div>)}</article><article><h3>관찰 항목</h3>{['선택 명확성', '근거 설명', '상대 발화 고려', '맥락 적합성'].map((item) => <div className="weight-row" key={item}><span>{item}</span><i><b style={{ width: `${55 + item.length * 6}%` }} /></i></div>)}<small>사용자 결과 화면에는 숫자 점수를 노출하지 않습니다.</small></article><article><h3>관계 변화 규칙</h3><div className="relation-rule positive"><span>＋</span><div><strong>솔직한 자기표현</strong><small>캐릭터 성향에 따라 관계 변화</small></div></div><div className="relation-rule positive"><span>＋</span><div><strong>상대 상황을 확인함</strong><small>신뢰와 편안함에 반영</small></div></div><div className="relation-rule negative"><span>−</span><div><strong>결정이나 책임을 반복 회피</strong><small>현재 시나리오의 진행에만 반영</small></div></div></article></div></section>}
        {section === 'preview' && <section className="builder-block preview-block"><div className="block-heading"><div><h2>시나리오 미리보기</h2><span>실제 웹 플레이 화면과 동일하게 캐릭터는 중앙, 화면 해설과 대사는 하단에 표시됩니다.</span></div></div><div className="preview-stage"><div className={`preview-scene mode-visual-${mode.toLowerCase()} ${(draft.turns[activeFlowSceneIndex]?.backgroundImage || draft.coverImage) ? 'has-uploaded-background' : ''}`} style={(draft.turns[activeFlowSceneIndex]?.backgroundImage || draft.coverImage) ? { backgroundImage: `linear-gradient(180deg, rgba(9,11,18,.03) 45%, rgba(9,11,18,.44) 100%), url(${draft.turns[activeFlowSceneIndex]?.backgroundImage || draft.coverImage})` } : undefined}><div className="preview-avatars">{activeCharacters.map((character, index) => <PersonAvatar key={character.id} name={character.name} image={character.image} accent={['violet', 'blue', 'mint'][index % 3]} large />)}</div><div className="preview-caption"><span>{draft.turns[activeFlowSceneIndex]?.situation}</span><strong>{draft.turns[activeFlowSceneIndex]?.line}</strong></div></div><div className="always-on-preview"><span className="listening-dot" /><div><strong>음성 자동 인식 중</strong><small>사용자가 말하면 별도 버튼 없이 자동으로 자막에 반영됩니다.</small></div><div className="mini-wave"><i /><i /><i /><i /></div></div><div className="preview-goal"><strong>이번 턴에서 사용자가 할 행동</strong><p>{draft.turns[activeFlowSceneIndex]?.userGoal}</p></div></div></section>}
      </main>
      <aside className="builder-inspector"><section><div className="inspector-title"><strong>✦ AI 자동 생성 요약</strong><button>수정하기</button></div><h3>사용자 응답 유형</h3>{['명확한 선택 + 이유 설명', '명확한 선택', '결정을 미룸 / 회피', '캐릭터에게 질문함', '농담 / 엉뚱한 대답', '맥락과 맞지 않는 대답'].map((item, index) => <div className="inspector-line" key={item}><i className={index < 2 ? 'green' : index < 4 ? 'yellow' : 'red'} />{item}</div>)}</section>{mode !== 'C' && <section><h3>최신 결과 정책</h3><ul><li>숫자 점수·그래프를 노출하지 않음</li><li>실제 발화 근거를 인용·요약</li><li>효과적이었던 부분 1~2개</li><li>명확할 때만 놓친 부분 1개</li><li>다른 결말 조건이나 공략 힌트 없음</li></ul></section>}{mode === 'C' && <section><h3>C 모드 참여 구조</h3><ul><li>캐릭터 {activeCharacters.length}명 설정</li><li>대표 화자: {activeCharacters.find((character) => character.id === leadCharacterIds.C)?.name ?? activeCharacters[0]?.name}</li><li>공통 시작 장면 1개</li><li>다른 캐릭터는 순차 참여</li></ul></section>}<button type="button" className="inspector-preview" onClick={() => setSection('preview')}>이 턴 미리보기</button></aside>
    </div>
  </div>
}

const responses: Record<string, string[][]> = {
  snack: [
    ['매운맛! 오늘 스트레스받아서 자극적인 게 먹고 싶어.', '치즈맛. 매운 건 맛보다 아픈 느낌이 먼저 와.', '네가 먹고 싶은 걸로 골라.'],
    ['매운맛은 먹고 나면 정신이 번쩍 들어서 좋아.', '고소한 맛이 오래 먹기 편해서 치즈맛을 골랐어.', '너는 왜 매운맛을 좋아하는데?'],
    ['좋아. 이걸로 정하고 같이 먹자.', '나는 다른 것도 조금 더 보고 싶은데?', '아무거나 괜찮아.'],
  ],
  lunch: [
    ['어제 국밥 먹었으니까 오늘은 파스타 어때? 민수가 싫으면 국밥 메뉴도 있는 곳을 찾아보자.', '각자 하나씩 고르고 바로 투표하자.', '나는 아무거나 괜찮아.'],
    ['지윤이가 먹을 수 있는 메뉴가 있는지 먼저 확인해보자.', '일단 파스타로 정했으니까 들어가서 생각하자.', '다른 식당을 처음부터 다시 찾아보자.'],
    ['10분 안에 갈 수 있고 견과류 없는 메뉴가 있는 양식집으로 가자.', '다수결대로 가장 가까운 파스타집으로 가자.', '결정은 다른 사람이 해줘.'],
  ],
  'first-talk': [
    ['내 이야기부터 해도 될까?', '너를 좀 더 알고 싶어. 먼저 이야기해줘.'],
    ['따뜻한 수프가 좋을 것 같아.', '샌드위치가 간단해서 좋을 것 같아.'],
    ['오늘은 그냥 네 이야기만 더 듣고 싶어.', '사실 나도 오늘 조금 지치는 일이 있었어.'],
  ],
}

function AlwaysListening({ transcript, state }: { transcript: string; state: VoiceState }) {
  const copy = state === 'unsupported' ? ['자동 음성 인식 미지원', '이 브라우저에서는 키보드 대체 입력을 사용해 주세요.'] : state === 'denied' ? ['마이크 권한 필요', '브라우저 주소창에서 마이크 권한을 허용하면 자동으로 다시 듣습니다.'] : state === 'starting' ? ['음성 인식 준비 중', '별도 버튼 없이 마이크 연결을 시작하고 있습니다.'] : ['음성 자동 인식 중', '버튼을 누르지 않아도 사용자의 말이 시작되면 자동으로 듣습니다.']
  return <div className={`listening-panel voice-${state}`}><div className="listening-state"><span className="listening-dot" /><div><strong>{copy[0]}</strong><small>{copy[1]}</small></div></div><div className="waveform">{Array.from({ length: 24 }).map((_, index) => <i key={index} style={{ height: `${8 + ((index * 13) % 24)}px` }} />)}</div><div className="live-transcript"><span>실시간 자막</span><p>{transcript || '말을 시작하면 이곳에 인식된 내용이 표시되고, 문장이 끝나면 자동으로 다음 턴으로 넘어갑니다.'}</p></div></div>
}

function ScenarioIntro({ scenario, onBack, onStart }: { scenario: Scenario; onBack: () => void; onStart: () => void }) {
  const endingCount = scenario.id === 'snack' ? 4 : scenario.id === 'lunch' ? 3 : 0
  const observationPoints = scenario.id === 'snack'
    ? ['선택을 미루지 않고 하나를 정하는지', '선택한 이유를 자기 말로 설명하는지', '상대 취향과 달라도 자기 기준을 유지하는지']
    : scenario.id === 'lunch'
      ? ['전달받은 여러 의견을 빠뜨리지 않고 정리하는지', '원하는 것과 불가능한 조건을 함께 확인하는지', '시간 안에 실행 가능한 최종안을 제안하는지']
      : ['사용자가 편한 방식으로 첫 대화에 진입하는지', '부담이 낮은 주제부터 자기 속도로 참여하는지', '평가 없이 관계와 대화를 이어가는지']
  return <div className="scenario-intro-page">
    <header className="simple-header"><Logo /><button type="button" className="outline-button intro-back-button" onClick={onBack}>← 시나리오 목록으로</button></header>
    <main className="intro-content">
      <div className="intro-breadcrumb"><ModeBadge mode={scenario.mode} /><span>{scenario.duration}</span></div>
      <h1>{scenario.title}</h1>
      <p className="intro-summary">{scenario.summary}</p>
      {scenario.coverImage && <figure className="intro-cover-image"><img src={scenario.coverImage} alt={`${scenario.title} 대표 배경`} /><figcaption><ModeBadge mode={scenario.mode} /><span>{scenario.characterNames.join(' · ')}와 함께 시작하는 장면</span></figcaption></figure>}
      <section className="intro-layout">
        <div className="intro-main">
          <section><span className="intro-label">관찰 포인트</span><ul>{observationPoints.map((point) => <li key={point}><span>◎</span>{point}</li>)}</ul></section>
          <section><span className="intro-label">진행 방식</span><div className="process-row"><div><b>1</b><strong>장면 확인</strong><small>화면 해설과 캐릭터 대화</small></div><i>→</i><div><b>2</b><strong>자동 음성 인식</strong><small>버튼 없이 말하면 자동 인식</small></div><i>→</i><div><b>3</b><strong>{scenario.mode === 'C' ? '자유 대화' : '결말과 피드백'}</strong><small>{scenario.mode === 'C' ? '평가 없이 이어가기' : '실제 발화 근거로 설명'}</small></div></div></section>
          {endingCount > 0 && <section><div className="locked-heading"><div><span className="intro-label">발견할 수 있는 결말</span><p>결말의 이름과 조건은 시작 전에 공개하지 않습니다.</p></div><strong>총 {endingCount}개</strong></div><div className="locked-ending-row">{Array.from({ length: endingCount }).map((_, index) => <div key={index}><span>▣</span><strong>잠긴 결말 {index + 1}</strong><small>플레이 후 발견</small></div>)}</div></section>}
        </div>
        <aside className="intro-side"><span className="intro-label">등장 캐릭터</span><div className="intro-characters">{scenario.characterNames.map((name, index) => <div key={name}><PersonAvatar name={name} accent={['violet', 'blue', 'mint'][index]} large /><strong>{name}</strong>{scenario.mode === 'C' && index === 0 && <small>대표 화자</small>}</div>)}</div><div className="intro-notice"><strong>시작하기 전에</strong><p>마이크 권한을 허용하면 대화 중 별도 버튼을 누르지 않아도 음성을 자동으로 인식합니다. 언제든 키보드로 대신 입력할 수 있습니다.</p></div><button type="button" className="primary-button intro-start" onClick={onStart}>{scenario.mode === 'C' ? '대화 시작하기' : '시나리오 시작하기'} →</button></aside>
      </section>
    </main>
  </div>
}

type SnackRound = {
  narration: string
  speaker: string
  line: string
  goal: string
}

type SnackAnswer = {
  turn: number
  text: string
  hasReason: boolean
}

const snackScenarioRounds: SnackRound[] = [
  {
    narration: '밤 10시 42분, 동네 편의점. 하루가 매운맛 과자와 치즈맛 과자를 양손에 들고 사용자를 바라본다.',
    speaker: '하루',
    line: '둘 중 하나만 골라줘. 이번에는 ‘아무거나’ 금지야. 3초 안에 하나 고르고 이유도 바로 말하기.',
    goal: '매운맛 또는 치즈맛 중 하나를 고르고 이유를 한 문장으로 말하기',
  },
  {
    narration: '중간 라운드 1 · 과자 진열대 앞.',
    speaker: '하루',
    line: '이번에는 싼 제품이랑 익숙하게 좋아하는 제품 중 하나. 어떤 걸 고를래?',
    goal: '가격과 익숙한 취향 중 더 중요한 기준을 고르고 이유 말하기',
  },
  {
    narration: '중간 라운드 2 · 같은 가격의 두 제품을 비교한다.',
    speaker: '하루',
    line: '용량이 큰 제품이랑 먹기 편한 제품이라면 어느 쪽이야?',
    goal: '용량과 편의성 중 하나를 고르고 이유 말하기',
  },
  {
    narration: '중간 라운드 3 · 처음 보는 신제품이 눈에 들어온다.',
    speaker: '하루',
    line: '새로운 맛에 도전할래, 아니면 실패하지 않는 익숙한 맛을 고를래?',
    goal: '새로운 맛과 익숙한 맛 중 하나를 고르고 이유 말하기',
  },
  {
    narration: '중간 라운드 4 · 하루가 자신이 좋아하는 제품을 가리킨다.',
    speaker: '하루',
    line: '내가 좋아하는 제품이랑 네가 좋아하는 제품이 다르면 어떤 걸 고를래?',
    goal: '상대 취향과 자기 취향을 고려해 하나를 고르고 이유 말하기',
  },
  {
    narration: '여러 상품군을 둘러본 두 사람에게 계산대의 점장이 말을 건다.',
    speaker: '하루',
    line: '지금까지 네가 말한 가격, 용량, 취향을 다 합치면 어떤 상품을 추천할래?',
    goal: '가격·용량·취향을 함께 고려해 최종 상품을 제안하기',
  },
]

function SnackSelectionScenario({ scenario, onExit, onFinish }: { scenario: Scenario; onExit: () => void; onFinish: (result: ResultData) => void }) {
  const [turn, setTurn] = useState(0)
  const [answers, setAnswers] = useState<SnackAnswer[]>([])
  const [avoidanceCount, setAvoidanceCount] = useState(0)
  const [typed, setTyped] = useState('')
  const [transcript, setTranscript] = useState('')
  const [voiceState, setVoiceState] = useState<VoiceState>('starting')
  const [reply, setReply] = useState<{ line: string; advance: boolean } | null>(null)
  const answerRef = useRef<(value: string) => void>(() => undefined)
  const round = snackScenarioRounds[turn]
  const hasReason = (value: string) => /(때문|해서|니까|라서|좋아|싫어|편해|익숙|실패|가격|용량|취향)/.test(value)
  const finishWithEnding = (records: SnackAnswer[], avoided: number) => {
    const joined = records.map((record) => record.text).join(' ')
    const reasonCount = records.filter((record) => record.hasReason).length
    const lastAnswer = records.at(-1)?.text ?? ''
    const managerRoute = ['가격', '용량', '취향'].every((keyword) => lastAnswer.includes(keyword)) && reasonCount >= 5
    const spicyCount = records.filter((record) => /(매운|자극|새로운|하루가 좋아|네가 좋아)/.test(record.text)).length
    const cheeseCount = records.filter((record) => /(치즈|담백|익숙|먹기 편|내가 좋아|내 취향)/.test(record.text)).length
    if (managerRoute) {
      onFinish({ scenario, ending: '편의점 점장', story: '점장이 사용자의 상품 분석을 듣더니 야간 매장 운영을 맡아보지 않겠냐고 제안합니다.', reason: '여러 상품군을 살피면서 모든 선택에 이유를 붙였고, 마지막 제안에 가격·용량·취향을 함께 반영했습니다.', effective: ['선택 기준을 한 가지로 고정하지 않고 상황에 맞게 비교했어요.', '마지막에는 여러 기준을 한 문장 안에 정리해 실행 가능한 상품을 제안했어요.'], evidence: lastAnswer, remember: '여러 조건이 있는 결정에서는 기준을 나열한 뒤 우선순위를 정해 제안해보세요.', reaction: '점장이 사용자의 구체적인 상품 분석에 관심을 보였습니다.', relation: '하루는 예상하지 못한 전개를 재미있어합니다.' })
      return
    }
    if (avoided >= 3) {
      onFinish({ scenario, ending: '편의점 12바퀴', story: '과자 코너에서 시작한 두 사람은 음료, 아이스크림, 도시락 코너까지 돌아 다시 과자 코너로 돌아왔습니다.', reason: '선택을 다른 사람에게 넘기거나 결정을 미루는 응답이 세 번 반복되어 상품을 정하지 못했습니다.', effective: ['상대의 생각을 물어보며 대화에 관심을 보인 부분은 좋았어요.'], evidence: records.at(-1)?.text ?? '결정을 다른 사람에게 넘겼어요.', missed: '이번 상황의 목표였던 “직접 하나를 고르고 이유 말하기”가 완료되지 않았어요.', remember: '정답이 없는 선택에서도 먼저 하나를 고르고 짧은 이유를 붙여보세요.', reaction: '“안 돼. 오늘은 네 선택 연습이잖아. 다시. 매운맛, 치즈맛, 하나.”', relation: '하루가 선택권을 다시 사용자에게 돌려줬습니다.' })
      return
    }
    const cheeseRoute = cheeseCount > spicyCount || joined.includes('치즈맛')
    onFinish({ scenario, ending: cheeseRoute ? '치즈 좋아 청년' : '불닭 동맹', story: cheeseRoute ? '하루는 끝까지 이해하지 못한 표정으로 치즈 과자를 바라봅니다. 하지만 다음 만남을 위해 신제품 치즈 과자를 따로 챙겨둡니다.' : '두 사람은 편의점 앞 테이블에서 가장 매운 과자를 동시에 뜯습니다. 하루는 다음에는 더 매운 제품을 찾아오겠다고 선언합니다.', reason: cheeseRoute ? '하루의 취향과 달라도 자신의 선택 기준을 유지하고, 각 선택의 이유를 구체적으로 설명했습니다.' : '매운맛과 새로운 선택을 일관되게 고르면서 자신의 이유를 구체적으로 설명했습니다.', effective: reasonCount >= 4 ? ['각 라운드에서 하나를 분명하게 골라 대화를 앞으로 진행시켰어요.', '가격·용량·취향처럼 서로 다른 기준에 자신의 이유를 붙였어요.'] : ['여러 선택지 중 하나를 직접 골라 대화를 진행시켰어요.'], evidence: records[0]?.text ?? '', missed: reasonCount < 3 ? '일부 선택에서는 무엇을 골랐는지는 분명했지만 그 이유가 충분히 드러나지 않았어요.' : undefined, remember: '취향이 달라도 선택과 이유를 분명히 말하면 좋은 자기표현이 됩니다.', reaction: cheeseRoute ? '“치즈맛이라고? 넌 핫한 사람인 줄 알았는데 조금 실망이야. 그래도 취향이 다르면 한 봉지씩 살 수 있으니까 나쁘진 않네.”' : '“역시. 오늘은 좀 화끈하게 가야지. 너, 생각보다 결단력 있네?”', relation: cheeseRoute ? '대화 평가는 높지만 하루의 개인 취향과는 달랐습니다.' : '하루의 취향과 선택이 맞아 즐거운 분위기가 이어졌습니다.' })
  }
  const submitAnswer = (rawValue: string) => {
    const value = rawValue.trim()
    if (!value || reply) return
    setTranscript(value)
    setTyped('')
    if (turn === 0) {
      const avoids = /(아무거나|네가 골라|네가 먹고|모르겠|상관없)/.test(value)
      const asksBack = /(너는 왜|왜 매운|넌 왜)/.test(value)
      if (avoids) {
        const nextAvoidanceCount = avoidanceCount + 1
        setAvoidanceCount(nextAvoidanceCount)
        const nextRecords = [...answers, { turn, text: value, hasReason: false }]
        setAnswers(nextRecords)
        if (nextAvoidanceCount >= 3) finishWithEnding(nextRecords, nextAvoidanceCount)
        else setReply({ line: '안 돼. 오늘은 네 선택 연습이잖아. 다시. 매운맛, 치즈맛, 하나.', advance: false })
        return
      }
      if (asksBack) {
        const nextRecords = [...answers, { turn, text: value, hasReason: true }]
        setAnswers(nextRecords)
        setReply({ line: '먹고 나면 정신이 번쩍 들어서. 자, 내 이야기는 했으니까 이제 네 선택.', advance: false })
        return
      }
      const choseSpicy = value.includes('매운')
      const choseCheese = value.includes('치즈')
      if (!choseSpicy && !choseCheese) {
        setReply({ line: '매운맛이랑 치즈맛 중 하나를 먼저 골라줘. 이유는 그다음에 말해도 돼.', advance: false })
        return
      }
      const nextRecords = [...answers, { turn, text: value, hasReason: hasReason(value) }]
      setAnswers(nextRecords)
      setReply({ line: choseSpicy ? '역시. 오늘은 좀 화끈하게 가야지. 너, 생각보다 결단력 있네?' : '치즈맛이라고? 내 취향과는 다르지만 이유가 분명하니까 납득했어. 한 봉지씩 사면 되겠네.', advance: true })
      return
    }
    const nextRecords = [...answers, { turn, text: value, hasReason: hasReason(value) }]
    setAnswers(nextRecords)
    if (turn >= snackScenarioRounds.length - 1) finishWithEnding(nextRecords, avoidanceCount)
    else setReply({ line: hasReason(value) ? '좋아, 네가 어떤 기준으로 고르는지 알겠어. 다음 비교도 네 기준대로 골라봐.' : '선택은 알겠어. 다음에는 왜 그렇게 골랐는지도 같이 말해줘.', advance: true })
  }
  const continueScenario = () => {
    if (!reply) return
    if (reply.advance) setTurn((current) => Math.min(current + 1, snackScenarioRounds.length - 1))
    setReply(null)
    setTranscript('')
    setVoiceState('starting')
  }
  answerRef.current = submitAnswer
  useEffect(() => {
    if (reply) return
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Recognition) { setVoiceState('unsupported'); return }
    const recognition = new Recognition()
    let active = true
    let submitted = false
    let blocked = false
    recognition.lang = 'ko-KR'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onstart = () => setVoiceState('listening')
    recognition.onresult = (event) => {
      let combined = ''
      let finalText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const text = event.results[index][0].transcript
        combined += text
        if (event.results[index].isFinal) finalText += text
      }
      if (combined.trim()) setTranscript(combined.trim())
      if (finalText.trim() && !submitted) { submitted = true; answerRef.current(finalText.trim()) }
    }
    recognition.onerror = (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') { blocked = true; setVoiceState('denied') }
    }
    recognition.onend = () => {
      if (active && !submitted && !blocked) {
        try { recognition.start() } catch { setVoiceState('starting') }
      }
    }
    try { recognition.start() } catch { setVoiceState('starting') }
    return () => { active = false; recognition.stop() }
  }, [reply, turn])
  const activeLine = reply?.line ?? round.line
  return <div className="runner-page snack-scenario-page">
    <header className="runner-header"><button type="button" className="back-button" onClick={onExit}>←</button><div><ModeBadge mode="A" /><strong>{scenario.title}</strong><span className="documented-badge">기획서 A-1 목업</span></div><div className="runner-progress"><span>{turn + 1} / {snackScenarioRounds.length}턴</span><i><b style={{ width: `${((turn + 1) / snackScenarioRounds.length) * 100}%` }} /></i></div><button type="button" className="outline-button" onClick={onExit}>나가기</button></header>
    <main className="scene-stage stage-snack-art"><div className={`scene-conversation-layer ${reply ? 'character-reaction' : 'user-listening'}`}><div className="scene-narration">{round.narration}</div><article className="live-caption-card haru-caption"><PersonAvatar name="하루" accent="violet" image={characterPortraits.하루} /><div><span>하루</span><p>{activeLine}</p></div></article>{!reply && <article className={`live-caption-card user-caption ${transcript ? 'has-speech' : ''}`}><PersonAvatar name="나" accent="slate" /><div><span>사용자 · 실시간 자막</span><p>{transcript ? `“${transcript}”` : voiceState === 'listening' ? '말하는 내용을 듣고 있어요…' : voiceState === 'denied' ? '마이크 권한이 필요합니다.' : '음성 인식을 준비하고 있어요…'}</p></div><b aria-label="음성 자동 인식 중">{voiceState === 'listening' ? 'LIVE' : '대기'}</b></article>}</div></main>
    <aside className="interaction-dock snack-interaction-dock"><div className="turn-guidance"><span>{reply ? '응답 확인' : '이번 턴'}</span><strong>{reply ? (reply.advance ? '하루의 반응을 확인하고 다음 비교로 이동합니다.' : '같은 질문에 다시 답합니다.') : round.goal}</strong></div>{reply ? <div className="captured-answer"><span>사용자 발화</span><p>“{transcript}”</p><small>{answers.at(-1)?.hasReason ? '선택과 이유가 함께 인식되었습니다.' : '선택은 기록되었으며 이유가 있는지 추가로 확인합니다.'}</small></div> : <AlwaysListening transcript={transcript} state={voiceState} />}<div className="text-response">{reply ? <button type="button" className="primary-button continue-button" onClick={continueScenario}>{reply.advance ? '다음 비교로 이동' : '다시 답하기'} →</button> : <form onSubmit={(event) => { event.preventDefault(); submitAnswer(typed) }}><label><span>키보드 대체 입력</span><input value={typed} onChange={(event) => setTyped(event.target.value)} placeholder="선택과 이유를 한 문장으로 입력하세요" /></label><button type="submit" disabled={!typed.trim()}>전송</button></form>}</div></aside>
  </div>
}

function ScenarioRunner({ scenario, onExit, onFinish }: { scenario: Scenario; onExit: () => void; onFinish: (result: ResultData) => void }) {
  const [turn, setTurn] = useState(0)
  const [answers, setAnswers] = useState<string[]>([])
  const [typed, setTyped] = useState('')
  const [transcript, setTranscript] = useState('')
  const [voiceState, setVoiceState] = useState<VoiceState>('starting')
  const answerRef = useRef<(value: string) => void>(() => undefined)
  const lines = scenario.id === 'snack' ? [
    { narration: '밤 10시 42분, 동네 편의점 과자 코너.', speakers: [{ name: '하루', line: '매운맛이랑 치즈맛 중 하나만 골라줘. 이번에는 “아무거나” 금지야. 이유도 바로 말하기!' }] },
    { narration: '하루가 선택한 과자를 내려다보다가 다시 사용자를 바라본다.', speakers: [{ name: '하루', line: '오~ 그걸 골랐어? 이유도 궁금한데?' }] },
    { narration: '하루가 과자를 계산대로 가져가며 마지막으로 확인한다.', speakers: [{ name: '하루', line: '그럼 이걸로 확실히 정한 거지?' }] },
  ] : scenario.id === 'lunch' ? [
    { narration: '정오가 지났지만 동아리의 점심 메뉴가 아직 정해지지 않았다.', speakers: [{ name: '지윤', line: '민수는 국밥, 하루는 파스타를 원하고 나는 10분 안에 나가고 싶어. 너라면 어떻게 정할래?' }] },
    { narration: '파스타로 의견이 모여 식당 앞까지 왔지만, 지윤이 메뉴판 앞에서 멈춘다.', speakers: [{ name: '지윤', line: '여기 견과류 들어간 메뉴가 꽤 많은데… 내가 먹을 수 있는 게 있나?' }] },
    { narration: '점심시간이 얼마 남지 않았다. 지윤이 최종 결정을 기다린다.', speakers: [{ name: '지윤', line: '시간 안에 실제로 갈 수 있는 선택으로 정리해줄래?' }] },
  ] : [
    { narration: '공방의 마지막 조명을 끄기 전, 루미가 사용자를 발견한다.', speakers: [{ name: '루미', line: '마침 나도 문을 닫으려던 참이었어. 처음부터 말하려니 좀 어색할 수 있겠다. 말하기 힘들면 내 이야기만 들어도 괜찮아.' }] },
    { narration: '루미가 작업대 위에 놓인 빈 찻잔을 보며 웃는다.', speakers: [{ name: '루미', line: '오늘은 오래된 괘종시계를 고치느라 점심도 놓쳤어. 따뜻한 수프랑 샌드위치 중에 뭘 고를 것 같아?' }] },
    { narration: '루미가 공방 앞 골목으로 천천히 걸음을 옮긴다.', speakers: [{ name: '루미', line: '가는 동안 내 이야기를 더 해도 되고, 이제 네 이야기를 들어도 돼. 어느 쪽이 편해?' }] },
  ]

  const makeResult = (finalAnswers: string[]) => {
    const joined = finalAnswers.join(' ')
    if (scenario.id === 'snack') {
      const cheese = joined.includes('치즈')
      const avoid = joined.includes('아무거나') || joined.includes('네가')
      onFinish({ scenario, ending: avoid ? '편의점 12바퀴' : cheese ? '치즈 좋아 청년' : '불닭 동맹', story: avoid ? '과자 코너에서 시작한 선택은 다른 코너를 돌아 다시 원점으로 돌아왔습니다.' : cheese ? '하루의 매운맛 권유에도 자기 취향을 유지하며 함께 먹을 간식을 정했습니다.' : '두 사람은 편의점 앞 테이블에서 가장 매운 과자를 함께 뜯었습니다.', reason: avoid ? '선택을 다른 사람에게 넘기는 응답이 반복되어 결정을 마무리하지 못했습니다.' : '하나를 명확하게 선택하고 자신의 이유를 구체적으로 설명했습니다.', effective: avoid ? ['상대가 왜 매운맛을 좋아하는지 질문해 대화 관심을 보였어요.'] : ['둘 중 하나를 명확하게 선택해 대화를 앞으로 진행시켰어요.', '자신의 경험이나 취향을 이유로 덧붙여 선택을 이해하기 쉽게 만들었어요.'], evidence: finalAnswers[0] ?? '', missed: avoid ? '이번 연습의 핵심인 “내가 선택하고 이유 말하기”를 상대에게 다시 넘겼어요.' : undefined, remember: avoid ? '정답이 없는 선택에서도 먼저 하나를 고르고, 짧은 이유를 붙여보세요.' : '취향이 달라도 자신의 선택과 이유를 분명히 말하면 충분히 좋은 대화가 됩니다.', reaction: avoid ? '“이번에는 네 선택 연습이잖아. 다시 하나만 골라봐.”' : cheese ? '“우리 취향은 다르지만, 네가 왜 좋아하는지는 확실히 알겠네.”' : '“역시. 오늘은 좀 화끈하게 가야지. 너, 생각보다 결단력 있네?”', relation: avoid ? '하루가 결정을 다시 사용자에게 돌려줬어요.' : '솔직한 자기표현 덕분에 조금 가까워졌어요.' })
    } else {
      const checked = joined.includes('먹을 수') || joined.includes('견과류')
      const avoid = joined.includes('아무거나') || joined.includes('다른 사람이')
      onFinish({ scenario, ending: avoid ? '아무거나 원정대' : checked ? '모두가 먹을 수 있는 식당' : '식당 앞에서 다시 고민하기', story: avoid ? '서로 결정을 넘기는 동안 점심시간이 계속 지나갔습니다.' : checked ? '취향과 시간, 음식 제한을 모두 확인해 실제로 갈 수 있는 식당을 정했습니다.' : '파스타로 메뉴를 정해 식당까지 왔지만, 지윤이 먹을 수 있는 메뉴를 다시 확인해야 했습니다.', reason: checked ? '여러 의견을 정리하는 데서 멈추지 않고 지윤의 음식 제한 조건까지 최종 선택에 반영했습니다.' : '결정은 진행했지만 앞에서 나온 제한 조건이 최종 선택에 충분히 반영되지 않았습니다.', effective: avoid ? ['다른 사람들의 의견을 들으려고 기다린 점은 긍정적이었어요.'] : ['의견이 엇갈릴 때 자신의 제안을 말해 대화를 앞으로 진행시켰어요.', '시간 안에 실행할 수 있는 구체적인 선택을 제시했어요.'], evidence: finalAnswers[0] ?? '', missed: checked ? undefined : '지윤이 말한 견과류 제한 조건을 메뉴 결정 과정에서 다시 확인하지 않았어요.', remember: checked ? '여러 사람이 함께 결정할 때는 원하는 것과 할 수 없는 것을 함께 확인하세요.' : '여러 사람이 함께 결정할 때는 누군가 하지 못하는 것이 없는지도 함께 확인하세요.', reaction: checked ? '지윤: “내가 먹을 수 있는 것까지 같이 봐줘서 고마워. 그럼 여기로 가자.”' : '지윤: “결정해준 건 고마운데, 다음에는 내가 먹을 수 있는지도 같이 봐줘.”', relation: checked ? '지윤과의 신뢰가 조금 깊어졌어요.' : '결정을 이끈 점은 긍정적이지만 지윤은 자신의 조건이 빠진 점을 불편해했어요.' })
    }
  }
  const answer = (value: string) => {
    const nextAnswers = [...answers, value]
    setAnswers(nextAnswers); setTranscript(value); setTyped('')
    if (turn >= lines.length - 1) {
      if (scenario.mode === 'C') { setTurn(0); setAnswers([]); setTranscript('루미가 조용히 다음 이야기를 기다리고 있어요.') }
      else makeResult(nextAnswers)
    } else setTurn((current) => current + 1)
  }
  answerRef.current = answer
  useEffect(() => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Recognition) { setVoiceState('unsupported'); return }
    const recognition = new Recognition()
    let active = true
    let submitted = false
    let blocked = false
    recognition.lang = 'ko-KR'
    recognition.continuous = true
    recognition.interimResults = true
    recognition.onstart = () => setVoiceState('listening')
    recognition.onresult = (event) => {
      let combined = ''
      let finalText = ''
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const text = event.results[index][0].transcript
        combined += text
        if (event.results[index].isFinal) finalText += text
      }
      if (combined.trim()) setTranscript(combined.trim())
      if (finalText.trim() && !submitted) {
        submitted = true
        answerRef.current(finalText.trim())
      }
    }
    recognition.onerror = (event) => {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') { blocked = true; setVoiceState('denied') }
    }
    recognition.onend = () => {
      if (active && !submitted && !blocked) {
        try { recognition.start() } catch { setVoiceState('starting') }
      }
    }
    try { recognition.start() } catch { setVoiceState('starting') }
    return () => { active = false; recognition.stop() }
  }, [scenario.id, turn])
  return <div className="runner-page">
    <header className="runner-header"><button type="button" className="back-button" onClick={onExit}>←</button><div><ModeBadge mode={scenario.mode} /><strong>{scenario.title}</strong></div><div className="runner-progress"><span>{turn + 1} / {lines.length}턴</span><i><b style={{ width: `${((turn + 1) / lines.length) * 100}%` }} /></i></div><button type="button" className="outline-button">나가기</button></header>
    <main className={`scene-stage stage-${scenario.mode.toLowerCase()}`}><div className="scene-people">{scenario.characterNames.map((name, index) => <div className={`scene-person person-${index}`} key={name}><PersonAvatar name={name} accent={['violet', 'blue', 'mint'][index]} large /><span>{name}</span></div>)}</div><div className="scene-dialogue-bar"><div className="scene-narration">{lines[turn].narration}</div><div className="speaker-area">{lines[turn].speakers.map((speaker, index) => <article className="speech-card" key={`${turn}-${speaker.name}`}><PersonAvatar name={speaker.name} accent={['violet', 'blue', 'mint'][index]} /><div><span>{speaker.name}</span><p>{speaker.line}</p></div></article>)}</div></div></main>
    <aside className="interaction-dock"><div className="turn-guidance"><span>이번 턴</span><strong>{scenario.id === 'snack' ? ['하나를 선택하고 이유 말하기', '선택한 이유를 구체적으로 설명하기', '결정을 마무리하기'][turn] : scenario.id === 'lunch' ? ['의견을 정리하고 자신의 제안 말하기', '제한 조건을 확인하고 보완하기', '실행 가능한 최종안 말하기'][turn] : ['대화 시작 방식을 선택하기', '부담이 낮은 선택으로 참여하기', '지금 편한 대화 방향 말하기'][turn]}</strong></div><AlwaysListening transcript={transcript} state={voiceState} /><div className="text-response">{scenario.mode === 'C' && <div className="c-entry-choices"><span>말하기가 어렵다면 방향만 선택해도 괜찮아요</span>{responses['first-talk'][turn].map((item) => <button type="button" key={item} onClick={() => answer(item)}>{item}</button>)}</div>}<form onSubmit={(event) => { event.preventDefault(); if (typed.trim()) answer(typed.trim()) }}><label><span>키보드 대체 입력</span><input value={typed} onChange={(event) => setTyped(event.target.value)} placeholder="마이크를 사용할 수 없을 때 입력하세요" /></label><button type="submit" disabled={!typed.trim()}>전송</button></form></div></aside>
  </div>
}

function CModeConversationRunner({ scenario, character, onExit }: { scenario: Scenario; character: Character; onExit: () => void }) {
  const opening = '마침 나도 문을 닫으려던 참이었어. 처음부터 말하려니 조금 어색할 수 있겠다. 말하기 힘들면 내 이야기만 들어도 괜찮아.'
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<MessageApi[]>([{
    id: 'opening', speaker_type: 'CHARACTER', speaker_id: character.id, content: opening, input_mode: 'SYSTEM',
  }])
  const [typed, setTyped] = useState('')
  const [status, setStatus] = useState<'connecting' | 'ready' | 'thinking' | 'error'>('connecting')
  const [error, setError] = useState('')
  const conversationRequest = useRef<ReturnType<typeof createConversation> | null>(null)

  useEffect(() => {
    if (!conversationRequest.current) {
      conversationRequest.current = createConversation(character.id, opening)
    }
    let active = true
    conversationRequest.current
      .then((conversation) => {
        if (!active) return
        setConversationId(conversation.id)
        setStatus('ready')
      })
      .catch((cause: unknown) => {
        if (!active) return
        setError(cause instanceof Error ? cause.message : '대화를 시작하지 못했습니다.')
        setStatus('error')
      })
    return () => { active = false }
  }, [character.id])

  const submit = async () => {
    const content = typed.trim()
    if (!content || !conversationId || status === 'thinking') return
    setTyped('')
    setStatus('thinking')
    try {
      const exchange = await sendTextMessage(conversationId, content)
      setMessages((current) => [...current, exchange.user_message, ...exchange.assistant_messages])
      setStatus('ready')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '메시지 전송에 실패했습니다.')
      setStatus('error')
    }
  }

  return <div className="runner-page c-api-runner">
    <header className="runner-header"><button type="button" className="back-button" onClick={onExit}>←</button><div><ModeBadge mode="C" /><strong>{scenario.title}</strong><span className="documented-badge">실제 API 연결</span></div><div className="runner-progress"><span>{status === 'connecting' ? '연결 중' : status === 'thinking' ? '답변 생성 중' : '자유 대화'}</span></div><button type="button" className="outline-button" onClick={onExit}>나가기</button></header>
    <main className="scene-stage stage-c"><div className="scene-people"><div className="scene-person person-0"><PersonAvatar name={character.name} accent={character.accent} image={character.image} large /><span>{character.name}</span></div></div><div className="scene-dialogue-bar"><div className="scene-narration">공방의 마지막 조명을 끄기 전, {character.name}가 사용자를 발견한다.</div><div className="c-message-list">{messages.map((message) => <article className={`speech-card ${message.speaker_type === 'USER' ? 'user-message' : ''}`} key={message.id}>{message.speaker_type === 'CHARACTER' && <PersonAvatar name={character.name} accent={character.accent} image={character.image} />}<div><span>{message.speaker_type === 'USER' ? '나' : character.name}</span><p>{message.content}</p></div></article>)}</div></div></main>
    <aside className="interaction-dock"><div className="turn-guidance"><span>C모드 텍스트 테스트</span><strong>{status === 'thinking' ? `${character.name}가 답변을 생각하고 있어요.` : '평가 없이 자유롭게 이야기합니다.'}</strong></div>{error && <div className="captured-answer"><span>연결 오류</span><p>{error}</p></div>}<div className="text-response"><form onSubmit={(event) => { event.preventDefault(); void submit() }}><label><span>사용자 메시지</span><input value={typed} onChange={(event) => setTyped(event.target.value)} placeholder="지금은 LLM 품질 확인을 위해 텍스트로 입력하세요" /></label><button type="submit" disabled={!typed.trim() || !conversationId || status === 'thinking'}>전송</button></form></div></aside>
  </div>
}

function ResultPage({ result, onRestart, onList }: { result: ResultData; onRestart: () => void; onList: () => void }) {
  const hiddenEndingCount = result.scenario.id === 'snack' ? 3 : result.scenario.id === 'lunch' ? 2 : 0
  return <div className="result-page"><header className="result-header"><Logo /><div><ModeBadge mode={result.scenario.mode} /><span>{result.scenario.title}</span></div><button type="button" className="outline-button" onClick={onList}>시나리오 목록</button></header><main className="result-content"><section className="ending-hero"><span>내가 도달한 결말</span><h1>{result.ending}</h1><p>{result.story}</p></section><section className="reason-card"><span>왜 이런 결말이 나왔을까요?</span><p>{result.reason}</p></section><div className="feedback-layout"><div><section className="feedback-card effective"><div className="feedback-label"><span>✓</span>이번 대화에서 효과적이었던 부분</div><ul>{result.effective.map((item) => <li key={item}>{item}</li>)}</ul><blockquote>“{result.evidence}”</blockquote></section>{result.missed && <section className="feedback-card missed"><div className="feedback-label"><span>!</span>한 번 더 생각해볼 부분</div><p>{result.missed}</p></section>}<section className="feedback-card remember"><div className="feedback-label"><span>→</span>다음에 비슷한 상황이 온다면</div><p>{result.remember}</p></section></div><aside><section className="feedback-card reaction"><span>캐릭터의 마지막 반응</span><p>{result.reaction}</p><div>{result.relation}</div></section></aside></div>{hiddenEndingCount > 0 && <section className="discovered-endings"><div><span>다른 이야기의 가능성</span><h2>아직 발견하지 않은 결말이 {hiddenEndingCount}개 있어요</h2><p>결말의 이름과 조건은 공개하지 않습니다. 다른 방식으로 대화하면 새로운 결과를 발견할 수 있습니다.</p></div><div className="locked-result-grid">{Array.from({ length: hiddenEndingCount }).map((_, index) => <article key={index}><span>▣</span><strong>잠긴 결말</strong><small>조건 비공개</small></article>)}</div></section>}<div className="result-actions"><button type="button" className="primary-button" onClick={onRestart}>처음부터 다시 하기</button><button type="button" className="outline-button" onClick={onList}>다른 시나리오 보기</button></div></main></div>
}

function characterFromApi(value: CharacterApi): Character {
  return {
    id: value.id,
    name: value.name,
    nickname: value.nickname ?? '',
    concept: value.concept,
    persona: value.persona,
    traits: value.traits,
    speech: value.speech_style,
    length: value.response_length,
    relation: value.relationship_style,
    voice: value.voice_label,
    accent: value.id === 'character_a' ? 'blue' : 'violet',
    updated: `v${value.version}`,
  }
}

function characterToApi(value: Character) {
  return {
    name: value.name,
    nickname: value.nickname || null,
    concept: value.concept,
    persona: value.persona,
    traits: value.traits,
    speech_style: value.speech,
    response_length: value.length,
    relationship_style: value.relation,
    voice_label: value.voice,
  }
}

function App() {
  const [page, setPage] = useState<Page>('home')
  const [characters, setCharacters] = useState<Character[]>(initialCharacters)
  const [scenarios] = useState<Scenario[]>(initialScenarios)
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null)
  const [runningScenario, setRunningScenario] = useState<Scenario | null>(null)
  const [result, setResult] = useState<ResultData | null>(null)
  const [toast, setToast] = useState('')
  useEffect(() => { window.scrollTo(0, 0) }, [page])
  useEffect(() => {
    let active = true
    listCharacters()
      .then((items) => {
        if (active) setCharacters(items.map(characterFromApi))
      })
      .catch(() => {
        if (active) setToast('백엔드 캐릭터를 불러오지 못해 화면 예시 데이터를 표시합니다.')
      })
    return () => { active = false }
  }, [])
  const run = (scenario: Scenario) => { setRunningScenario(scenario); setResult(null); setPage('intro') }
  const navigate = (next: Page) => { setPage(next); setResult(null); setRunningScenario(null) }
  const saveCharacter = async (character: Character) => {
    try {
      const isNew = character.id.startsWith('character-') && !['character_a', 'character_b'].includes(character.id)
      const saved = isNew
        ? await createCharacter(characterToApi(character))
        : await updateCharacter(character.id, characterToApi(character))
      const mapped = characterFromApi(saved)
      setCharacters((current) => current.some((item) => item.id === character.id)
        ? current.map((item) => item.id === character.id ? mapped : item)
        : [mapped, ...current])
      setToast(`${mapped.name} 설정을 DB에 v${saved.version}으로 저장했습니다.`)
      navigate('characters')
    } catch (cause) {
      setToast(cause instanceof Error ? cause.message : '캐릭터 저장에 실패했습니다.')
    }
  }
  const shellVisible = !['builder', 'intro', 'run', 'result'].includes(page)
  const content = useMemo(() => {
    if (page === 'home') return <HomePage scenarios={scenarios} onRun={run} onNavigate={navigate} />
    if (page === 'characters') return <CharacterList characters={characters} onEdit={(character) => { setEditingCharacter(character); setPage('characterEditor') }} onCreate={() => { setEditingCharacter(null); setPage('characterEditor') }} />
    if (page === 'characterEditor') return <CharacterEditor character={editingCharacter} onCancel={() => navigate('characters')} onSave={saveCharacter} />
    if (page === 'scenarios') return <ScenarioLibrary scenarios={scenarios} onRun={run} onEdit={() => navigate('builder')} />
    return null
  }, [characters, editingCharacter, page, scenarios])
  if (page === 'builder') return <ScenarioBuilder onBack={() => navigate('scenarios')} onSaved={() => { setToast('시나리오 설정을 저장했습니다.'); navigate('scenarios') }} />
  if (page === 'intro' && runningScenario) return <ScenarioIntro scenario={runningScenario} onBack={() => navigate('scenarios')} onStart={() => setPage('run')} />
  if (page === 'run' && runningScenario) {
    const runnerProps = { scenario: runningScenario, onExit: () => navigate('scenarios'), onFinish: (data: ResultData) => { setResult(data); setPage('result') } }
    if (runningScenario.mode === 'C') {
      const character = characters.find((item) => runningScenario.characterNames.includes(item.name)) ?? characters[0]
      return character ? <CModeConversationRunner scenario={runningScenario} character={character} onExit={() => navigate('scenarios')} /> : null
    }
    return runningScenario.id === 'snack' ? <SnackSelectionScenario {...runnerProps} /> : <ScenarioRunner {...runnerProps} />
  }
  if (page === 'result' && result) return <ResultPage result={result} onRestart={() => { setResult(null); setRunningScenario(result.scenario); setPage('run') }} onList={() => navigate('scenarios')} />
  return <div className="web-app">{shellVisible && <Sidebar page={page} onNavigate={navigate} />}<div className="main-shell">{shellVisible && <TopHeader page={page} onNavigate={navigate} />}<main className="page-scroll">{content}</main></div>{toast && <button type="button" className="toast" onClick={() => setToast('')}><span>✓</span>{toast}</button>}</div>
}

export default App
