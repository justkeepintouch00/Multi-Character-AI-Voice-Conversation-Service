import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

type Page = 'home' | 'characters' | 'scenarios' | 'builder' | 'characterEditor' | 'intro' | 'run' | 'result'
type Mode = 'A' | 'B' | 'C'
type BuilderSection = 'overview' | 'characters' | 'flow' | 'endings' | 'assets' | 'rules' | 'preview'

type Character = {
  id: string
  name: string
  nickname: string
  concept: string
  traits: string[]
  speech: string
  length: string
  relation: string
  voice: string
  accent: string
  updated: string
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
}

type TurnDraft = { situation: string; line: string; userGoal: string; background: string }
type EndingDraft = { name: string; description: string; condition: string }
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
}

type ScenarioCharacterDraft = {
  id: string
  name: string
  concept: string
  traits: string[]
  speech: string
  relation: string
  voice: string
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
    traits: ['장난스러운', '솔직한', '활발한'], speech: '반말', length: '보통', relation: '장난을 많이 치는 동생',
    voice: '밝고 또렷한 목소리', accent: 'violet', updated: '오늘 수정',
  },
  {
    id: 'lumi', name: '루미', nickname: '',
    concept: '오래된 골목에서 시계 공방을 운영한다. 식사를 자주 거르고 밤늦게 혼자 산책하며, 조용하지만 상대의 말을 오래 기억한다.',
    traits: ['다정한', '차분한', '섬세한'], speech: '관계에 따라 변화', length: '보통', relation: '차분하게 이끌어주는 선배',
    voice: '낮고 차분한 목소리', accent: 'blue', updated: '어제 수정',
  },
  {
    id: 'jiyoon', name: '지윤', nickname: '지유',
    concept: '동아리의 총무를 맡고 있다. 의견을 강하게 주장하지 않지만 시간과 음식 제한처럼 실제로 지켜야 할 조건을 꼼꼼하게 기억한다.',
    traits: ['차분한', '솔직한', '섬세한'], speech: '반말', length: '짧게 말함', relation: '조용히 곁을 지키는 동료',
    voice: '부드럽고 편안한 목소리', accent: 'mint', updated: '3일 전 수정',
  },
]

const initialScenarios: Scenario[] = [
  { id: 'snack', mode: 'A', title: '오늘의 간식 선발전', summary: '제한 시간 안에 간식을 고르고 자기 이유를 분명하게 말해보는 짧은 연습', characterNames: ['하루'], duration: '약 5분', published: true, plays: 128 },
  { id: 'lunch', mode: 'B', title: '오늘 점심은 반드시 정한다', summary: '지윤이 전해준 서로 다른 의견과 제한 조건을 확인해 실행할 수 있는 결정을 만드는 상황', characterNames: ['지윤'], duration: '약 8분', published: true, plays: 84 },
  { id: 'first-talk', mode: 'C', title: '공방이 문을 닫은 뒤', summary: '말할 준비가 될 때까지 루미의 일상을 따라가며 천천히 대화를 시작하는 이야기', characterNames: ['루미'], duration: '자유 대화', published: true, plays: 203 },
]

const initialDrafts: Record<Mode, ScenarioDraft> = {
  A: {
    title: '오늘의 간식 선발전', summary: '제한 시간 안에 간식을 고르고 이유를 말해보자!', openingGuide: '두 가지 간식 중 하나를 직접 고르고, 캐릭터에게 선택한 이유를 말하는 연습입니다.', estimatedDuration: '약 5분', practiceType: '빠르게 결정하기', characters: '하루', useAffinity: true,
    background: '동네 편의점 · 과자 코너',
    turns: [
      { situation: '하루가 두 가지 과자를 들고 사용자를 바라본다.', line: '매운맛이랑 치즈맛 중 하나 골라줘. 이유도 바로 말해야지?', userGoal: '둘 중 하나를 선택하고 이유를 말하기', background: '편의점 과자 코너' },
      { situation: '하루가 네 선택을 기다리며 궁금해한다.', line: '오~ 이유도 궁금한데? 왜 그걸 골랐어?', userGoal: '선택한 이유를 구체적으로 설명하기', background: '편의점 과자 코너' },
      { situation: '하루가 간식을 계산대로 가져간다.', line: '좋아, 그럼 이거나 같이 먹으면서 얘기하자.', userGoal: '결정에 동의하거나 다른 의견 말하기', background: '편의점 계산대' },
    ],
    endings: [
      { name: '불닭 동맹', description: '매운맛을 자주 선택하고 자기 이유를 분명하게 말해 하루와 취향이 잘 맞았다.', condition: '매운맛 선택을 반복하고 근거를 구체적으로 설명했을 때' },
      { name: '치즈 좋아 청년', description: '하루의 권유에도 자기 취향을 유지하면서 대화를 자연스럽게 이어갔다.', condition: '치즈맛을 선택하고 자기 취향을 일관되게 설명했을 때' },
      { name: '편의점 12바퀴', description: '선택을 계속 미루다 다른 코너까지 둘러보고 다시 과자 코너로 돌아왔다.', condition: '결정 회피가 반복되었을 때' },
    ],
  },
  B: {
    title: '오늘 점심은 반드시 정한다', summary: '지윤과 대화하며 엇갈리는 의견과 제한 조건을 조율해 점심 메뉴를 결정해보자.', openingGuide: '지윤이 전달하는 여러 사람의 의견을 정리하고, 시간과 음식 제한까지 반영해 실행 가능한 결정을 만듭니다.', estimatedDuration: '약 8분', practiceType: '의견 조율하기', characters: '지윤', useAffinity: true,
    background: '대학교 동아리방 · 점심시간',
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
    background: '시계 공방 · 저녁',
    turns: [
      { situation: '루미가 공방 문을 닫으며 사용자를 반긴다.', line: '처음부터 말하려니 어색할 수 있겠다. 내 이야기만 먼저 들어도 괜찮아.', userGoal: '내 이야기부터 할지, 루미를 더 알아갈지 선택하기', background: '시계 공방' },
      { situation: '루미가 오늘 점심을 놓쳤다고 이야기한다.', line: '따뜻한 수프랑 샌드위치 중에 뭘 고를 것 같아?', userGoal: '부담이 낮은 선택으로 대화에 참여하기', background: '공방 앞 골목' },
    ], endings: [],
  },
}

const traitOptions = ['다정한', '차분한', '장난스러운', '솔직한', '성숙한', '의젓한', '활발한', '집착기 있는', '무뚝뚝한', '섬세한', '엉뚱한', '수줍은', '보호자 같은', '친구 같은', '츤데레 느낌']

function Logo() {
  return <div className="logo-lockup"><span className="logo-symbol">O</span><strong>온기</strong></div>
}

function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={`mode-badge mode-${mode.toLowerCase()}`}>{mode} 모드</span>
}

function PersonAvatar({ name, accent = 'violet', large = false }: { name: string; accent?: string; large?: boolean }) {
  return <span className={`person-avatar ${accent} ${large ? 'large' : ''}`} aria-hidden="true">{name.slice(0, 1)}</span>
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
    <div className="character-grid">{characters.map((character) => <article className="character-card" key={character.id}><div className={`character-cover ${character.accent}`}><PersonAvatar name={character.name} accent={character.accent} large /><span>{character.updated}</span></div><div className="character-card-body"><div><h3>{character.name}</h3><span>{character.relation}</span></div><p>{character.concept}</p><div className="trait-row">{character.traits.map((trait) => <span key={trait}>{trait}</span>)}</div><dl><div><dt>말투</dt><dd>{character.speech}</dd></div><div><dt>목소리</dt><dd>{character.voice}</dd></div></dl><button type="button" className="edit-button" onClick={() => onEdit(character)}>캐릭터 설정 수정</button></div></article>)}</div>
  </div>
}

function Field({ label, required, help, children }: { label: string; required?: boolean; help?: string; children: React.ReactNode }) {
  return <label className="form-field"><span className="form-label">{label}{required && <em>필수</em>}</span>{children}{help && <small>{help}</small>}</label>
}

function CharacterEditor({ character, onCancel, onSave }: { character: Character | null; onCancel: () => void; onSave: (character: Character) => void }) {
  const [form, setForm] = useState<Character>(character ?? { id: `character-${Date.now()}`, name: '', nickname: '', concept: '', traits: [], speech: '반말', length: '보통', relation: '편한 친구', voice: '부드럽고 편안한 목소리', accent: 'violet', updated: '방금 수정' })
  const update = <K extends keyof Character>(key: K, value: Character[K]) => setForm((current) => ({ ...current, [key]: value }))
  const toggleTrait = (trait: string) => update('traits', form.traits.includes(trait) ? form.traits.filter((item) => item !== trait) : form.traits.length < 4 ? [...form.traits, trait] : form.traits)
  const valid = form.name.trim() && form.concept.trim().length >= 20 && form.traits.length > 0
  return <div className="page editor-page">
    <div className="editor-titlebar"><button type="button" className="back-button" onClick={onCancel}>←</button><div><span className="section-eyebrow">CHARACTER CUSTOMIZATION</span><h1>{character ? `${character.name} 설정 수정` : '새 캐릭터 만들기'}</h1><p>저장한 설정은 이 캐릭터가 등장하는 A·B·C 모드에 공통 적용됩니다.</p></div><div><button type="button" className="outline-button" onClick={onCancel}>취소</button><button type="button" disabled={!valid} className="primary-button" onClick={() => onSave({ ...form, updated: '방금 수정' })}>설정 저장</button></div></div>
    <div className="editor-layout">
      <aside className="editor-summary"><div className={`character-preview ${form.accent}`}><PersonAvatar name={form.name || '?'} accent={form.accent} large /><strong>{form.name || '이름을 입력하세요'}</strong><span>{form.relation}</span></div><div className="completion-box"><div><strong>설정 완성도</strong><span>{valid ? '100%' : '60%'}</span></div><i><b style={{ width: valid ? '100%' : '60%' }} /></i><p>이름, 콘셉트, 핵심 성격을 입력하면 저장할 수 있습니다.</p></div><div className="editor-menu"><button className="active">기본 정보</button><button>성격과 대화</button><button>관계 스타일</button><button>목소리와 외형</button><button>추가 설정</button></div></aside>
      <main className="editor-form">
        <section className="form-section"><div className="form-section-title"><span>01</span><div><h2>기본 정보</h2><p>캐릭터의 이름과 삶을 하나의 명확한 콘셉트로 작성합니다.</p></div></div><div className="two-column"><Field label="이름" required><input value={form.name} onChange={(event) => update('name', event.target.value)} placeholder="예: 루미" /></Field><Field label="별명" help="선택 사항"><input value={form.nickname} onChange={(event) => update('nickname', event.target.value)} placeholder="친해졌을 때 부를 이름" /></Field></div><Field label="캐릭터 콘셉트" required help={`${form.concept.length}/200 · 권장 50~200자`}><textarea rows={5} maxLength={200} value={form.concept} onChange={(event) => update('concept', event.target.value)} placeholder="이 캐릭터는 어디에서 어떤 삶을 살고 있나요?" /></Field></section>
        <section className="form-section"><div className="form-section-title"><span>02</span><div><h2>성격과 대화</h2><p>서로 모순되지 않도록 핵심 성격은 최대 4개만 선택합니다.</p></div></div><Field label="핵심 성격" required help={`${form.traits.length}/4 선택`}><div className="select-chips">{traitOptions.map((trait) => <button type="button" className={form.traits.includes(trait) ? 'selected' : ''} key={trait} onClick={() => toggleTrait(trait)}>{trait}</button>)}</div></Field><div className="three-column"><Field label="말투"><select value={form.speech} onChange={(event) => update('speech', event.target.value)}><option>반말</option><option>존댓말</option><option>관계에 따라 변화</option></select></Field><Field label="말의 길이"><select value={form.length} onChange={(event) => update('length', event.target.value)}><option>짧게 말함</option><option>보통</option><option>길게 자세히 말함</option></select></Field><Field label="관계 스타일"><select value={form.relation} onChange={(event) => update('relation', event.target.value)}><option>편한 친구</option><option>다정하게 챙겨주는 연상</option><option>장난을 많이 치는 동생</option><option>조용히 곁을 지키는 동료</option><option>차분하게 이끌어주는 선배</option><option>함께 생활하는 룸메이트</option><option>처음 만나 천천히 친해지는 사이</option></select></Field></div></section>
        <section className="form-section"><div className="form-section-title"><span>03</span><div><h2>목소리와 외형</h2><p>목소리는 샘플을 듣고 선택하고, 캐릭터 이미지는 배경과 분리해 등록합니다.</p></div></div><div className="voice-grid">{['밝고 또렷한 목소리', '낮고 차분한 목소리', '부드럽고 편안한 목소리', '졸린 듯 느긋한 목소리'].map((voice) => <button type="button" key={voice} className={form.voice === voice ? 'selected' : ''} onClick={() => update('voice', voice)}><span>▶</span><div><strong>{voice}</strong><small>8초 샘플 듣기</small></div><i>{form.voice === voice ? '선택됨' : ''}</i></button>)}</div><div className="upload-grid"><label className="upload-panel"><input type="file" accept="image/*" /><span>＋</span><strong>캐릭터 이미지 등록</strong><small>배경 없는 PNG 권장 · 최대 10MB</small></label><div className="asset-explanation"><strong>캐릭터와 배경은 별도 자산입니다</strong><p>캐릭터 이미지는 한 번 등록하고 여러 시나리오 배경에 재사용합니다. 장면 미리보기에서 두 레이어를 자동으로 합성하며, 별도 소품 등록은 사용하지 않습니다.</p></div></div></section>
        <section className="form-section"><div className="form-section-title"><span>04</span><div><h2>추가 캐릭터성</h2><p>위 설정으로 표현하기 어려운 습관이나 금지 행동만 간결하게 추가합니다.</p></div></div><Field label="추가 프롬프트" help="선택 사항 · 최대 500자"><textarea rows={4} maxLength={500} placeholder="예: 사용자가 침묵하면 재촉하지 않고 자신의 일상 이야기를 짧게 들려준다." /></Field></section>
      </main>
    </div>
  </div>
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
  const draft = drafts[mode]
  const activeCharacters = scenarioCharacters[mode]
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
  const sections: { key: BuilderSection; icon: string; label: string }[] = [
    { key: 'overview', icon: '▤', label: '개요' }, { key: 'characters', icon: '◉', label: '캐릭터 설정' }, { key: 'flow', icon: '◇', label: '대화 흐름' }, { key: 'endings', icon: '⚑', label: '결말 설정' },
    { key: 'assets', icon: '▧', label: '배경 이미지' }, { key: 'rules', icon: '⚙', label: '설정·규칙' }, { key: 'preview', icon: '▷', label: '미리보기' },
  ]
  return <div className="builder-page">
    <header className="builder-top"><button type="button" className="back-button" onClick={onBack}>←</button><strong>시나리오 제작</strong><div className="mode-tabs">{(['A', 'B', 'C'] as Mode[]).map((item) => <button type="button" key={item} className={mode === item ? 'active' : ''} onClick={() => { setMode(item); setSection('overview') }}>{item} 모드</button>)}</div><div className="builder-actions"><button type="button" className="outline-button" onClick={() => setSection('preview')}>▷ 미리보기</button><button type="button" className="outline-button" onClick={onSaved}>저장</button><button type="button" className="primary-button" onClick={onSaved}>게시하기</button></div></header>
    <div className="builder-workspace">
      <aside className="builder-side"><nav>{sections.map((item) => <button type="button" key={item.key} disabled={mode === 'C' && item.key === 'endings'} className={section === item.key ? 'active' : ''} onClick={() => setSection(item.key)}><span>{item.icon}</span>{item.label}</button>)}</nav><div className="guide-card"><span>☼</span><strong>제작 가이드</strong><p>{mode === 'C' ? 'C 모드는 하나의 시작 장면과 대표 화자를 정합니다. 다른 캐릭터는 동시에 소개하지 않고 대화 흐름에 맞춰 참여합니다.' : 'A·B 모드는 주 캐릭터 한 명과 장면별 사용자 참여 목표를 반드시 설정합니다.'}</p><button type="button">가이드 보기</button></div></aside>
      <main className="builder-main">
        {section === 'overview' && <section className="builder-block"><div className="block-heading"><div><h2>1. 시나리오 개요</h2><span>플레이를 시작하기 전에 사용자에게 보여줄 정보입니다.</span></div><span>{mode === 'C' ? '평가 없는 자유 대화' : `${mode} 모드 시나리오`}</span></div><div className="builder-form-grid"><Field label="시나리오 제목" required><input value={draft.title} onChange={(event) => updateDraft({ title: event.target.value })} /></Field><Field label="한 줄 설명" required><input value={draft.summary} onChange={(event) => updateDraft({ summary: event.target.value })} /></Field><Field label="시작 전 안내" required help="사용자가 무엇을 하게 되는지 알려주되 결말 조건은 공개하지 않습니다."><textarea rows={4} value={draft.openingGuide} onChange={(event) => updateDraft({ openingGuide: event.target.value })} /></Field><div className="overview-side-fields"><Field label="예상 소요 시간"><input value={draft.estimatedDuration} onChange={(event) => updateDraft({ estimatedDuration: event.target.value })} /></Field><Field label={mode === 'A' ? '연습 유형' : mode === 'B' ? '상황 유형' : '대화 유형'}><select value={draft.practiceType} onChange={(event) => updateDraft({ practiceType: event.target.value })}><option>{draft.practiceType}</option><option>이유를 설명하기</option><option>자연스럽게 대화 이어가기</option><option>의견 조율하기</option><option>평가 없는 자유 대화</option></select></Field></div>{mode !== 'C' && <label className="toggle-field"><span><strong>관계 변화 사용</strong><small>대화 피드백과 별도로 캐릭터의 마지막 반응에 반영합니다.</small></span><button type="button" className={draft.useAffinity ? 'toggle active' : 'toggle'} onClick={() => updateDraft({ useAffinity: !draft.useAffinity })}><i /></button></label>}</div><div className="builder-note"><strong>결말 정보 공개 기준</strong><p>사용자는 시작 전에 결말의 총개수만 볼 수 있습니다. 이름, 달성 조건, 공략 힌트는 플레이 전후 모두 잠금 상태로 유지합니다.</p></div></section>}
        {section === 'characters' && <section className="builder-block character-builder"><div className="block-heading"><div><h2>2. 캐릭터 설정</h2><span>{mode === 'C' ? '1~3명 · 대표 화자 1명' : '주 캐릭터 정확히 1명'}</span></div>{mode === 'C' && <button type="button" className="soft-button" onClick={addCCharacter} disabled={activeCharacters.length >= 3}>＋ 캐릭터 추가</button>}</div><div className="character-source-tabs"><button type="button" className={characterSources[mode] === 'new' ? 'active' : ''} onClick={() => setCharacterSources((current) => ({ ...current, [mode]: 'new' }))}>시나리오 안에서 새로 만들기</button><button type="button" className={characterSources[mode] === 'existing' ? 'active' : ''} onClick={() => setCharacterSources((current) => ({ ...current, [mode]: 'existing' }))}>기존 캐릭터 불러오기</button></div>{characterSources[mode] === 'existing' && <div className="existing-character-picker"><label><span>캐릭터 라이브러리</span><select value={activeCharacters[0]?.id ?? ''} onChange={(event) => importCharacter(event.target.value)}>{initialCharacters.map((character) => <option key={character.id} value={character.id}>{character.name} · {character.relation}</option>)}</select></label><p>불러온 설정은 이 시나리오 안에서 수정해도 원본 캐릭터에는 영향을 주지 않습니다.</p></div>}<div className="scenario-character-list">{activeCharacters.map((character, index) => <article className="scenario-character-config" key={character.id}><header><div><PersonAvatar name={character.name || '?'} accent={['violet', 'blue', 'mint'][index]} /><span><strong>{character.name || `캐릭터 ${index + 1}`}</strong><small>{mode === 'C' && leadCharacterIds.C === character.id ? '공통 시작 장면의 대표 화자' : mode === 'C' ? '대화 중 순차 참여' : '주 캐릭터'}</small></span></div><div>{mode === 'C' && <label className="lead-speaker-radio"><input type="radio" name="lead-character" checked={leadCharacterIds.C === character.id} onChange={() => setLeadCharacterIds((current) => ({ ...current, C: character.id }))} /> 대표 화자</label>}{mode === 'C' && activeCharacters.length > 1 && <button type="button" className="remove-character" onClick={() => removeCCharacter(index)}>삭제</button>}</div></header><div className="character-config-grid"><Field label="이름" required><input value={character.name} onChange={(event) => updateScenarioCharacter(index, { name: event.target.value })} /></Field><Field label="관계 스타일"><select value={character.relation} onChange={(event) => updateScenarioCharacter(index, { relation: event.target.value })}><option>처음 만나 천천히 친해지는 사이</option><option>편한 친구</option><option>조용히 곁을 지키는 동료</option><option>차분하게 이끌어주는 선배</option><option>함께 생활하는 룸메이트</option></select></Field><Field label="캐릭터 성격과 상황" required help="C 모드는 성격만 설정해도 시작할 수 있습니다."><textarea rows={4} value={character.concept} onChange={(event) => updateScenarioCharacter(index, { concept: event.target.value })} placeholder="성격, 관심사, 사용자와의 현재 관계를 작성하세요." /></Field><div className="character-voice-fields"><Field label="말투"><select value={character.speech} onChange={(event) => updateScenarioCharacter(index, { speech: event.target.value })}><option>반말</option><option>존댓말</option><option>관계에 따라 변화</option></select></Field><Field label="목소리"><select value={character.voice} onChange={(event) => updateScenarioCharacter(index, { voice: event.target.value })}><option>밝고 또렷한 목소리</option><option>낮고 차분한 목소리</option><option>부드럽고 편안한 목소리</option><option>졸린 듯 느긋한 목소리</option></select></Field></div></div><Field label="핵심 성격" help={`${character.traits.length}/4 선택`}><div className="select-chips compact">{traitOptions.map((trait) => <button type="button" key={trait} className={character.traits.includes(trait) ? 'selected' : ''} onClick={() => updateScenarioCharacter(index, { traits: character.traits.includes(trait) ? character.traits.filter((item) => item !== trait) : character.traits.length < 4 ? [...character.traits, trait] : character.traits })}>{trait}</button>)}</div></Field></article>)}</div>{mode === 'C' && <div className="builder-note c-opening-rule"><strong>C 모드의 시작 장면 규칙</strong><p>캐릭터마다 별도 시작 시나리오를 동시에 실행하지 않습니다. 하나의 공통 시작 장면에서 대표 화자 한 명만 먼저 대화를 시작하고, 나머지 캐릭터는 장면 디렉터가 대화 맥락에 맞춰 순차적으로 참여시킵니다.</p></div>}<div className="builder-note"><strong>저장 방식</strong><p>캐릭터 설정은 이 시나리오와 함께 저장됩니다. 완성 후 원하면 캐릭터 라이브러리에 재사용 가능한 템플릿으로 별도 저장할 수 있습니다.</p></div></section>}
        {section === 'flow' && <section className="builder-block"><div className="block-heading"><div><h2>3. 대화 흐름</h2><span>총 {draft.turns.length}턴 · 사용자 참여 필수</span></div><button type="button" className="soft-button" onClick={() => updateDraft({ turns: [...draft.turns, { situation: '새 장면을 설명해 주세요.', line: '캐릭터가 할 말을 작성해 주세요.', userGoal: '사용자가 직접 해야 할 행동을 작성해 주세요.', background: draft.background }] })}>＋ 대화 턴 추가</button></div>{mode === 'C' && <div className="flow-structure-note"><span>대표 화자</span><strong>{activeCharacters.find((character) => character.id === leadCharacterIds.C)?.name ?? activeCharacters[0]?.name}</strong><p>첫 턴은 대표 화자만 시작합니다. 이후 턴에서 다른 캐릭터를 한 명씩 참여시켜 대사가 겹치지 않도록 구성합니다.</p></div>}<div className="turn-list">{draft.turns.map((turn, index) => <article className="turn-row" key={`${mode}-${index}`}><div className="turn-index"><span>{index + 1}</span><i>⋮⋮</i></div><div className={`turn-visual mode-visual-${mode.toLowerCase()}`}><PersonAvatar name={activeCharacters[0]?.name ?? '?'} accent={index % 2 ? 'blue' : 'violet'} large /><small>{turn.background}</small></div><div className="turn-fields"><Field label="화면 상황 설명"><input value={turn.situation} onChange={(event) => updateTurn(index, { situation: event.target.value })} /></Field><Field label="캐릭터 대사"><textarea rows={2} value={turn.line} onChange={(event) => updateTurn(index, { line: event.target.value })} /></Field><Field label="사용자가 해야 하는 행동" required><input value={turn.userGoal} onChange={(event) => updateTurn(index, { userGoal: event.target.value })} /></Field></div><div className="turn-asset"><strong>장면 자산</strong><div className="asset-layer"><span className="bg-thumb" /><div><b>배경</b><small>{turn.background}</small></div></div><div className="asset-layer"><PersonAvatar name={activeCharacters[0]?.name ?? '?'} accent="violet" /><div><b>캐릭터</b><small>{activeCharacters.map((character) => character.name).join(' · ')}</small></div></div><button type="button">배경 변경</button><small>소품 등록 없음</small></div></article>)}</div><button type="button" className="wide-add" onClick={() => updateDraft({ turns: [...draft.turns, { situation: '새 장면을 설명해 주세요.', line: '캐릭터가 할 말을 작성해 주세요.', userGoal: '사용자가 직접 해야 할 행동을 작성해 주세요.', background: draft.background }] })}>＋ 대화 턴 추가</button></section>}
        {section === 'endings' && mode !== 'C' && <section className="builder-block ending-builder"><div className="block-heading"><div><h2>결말 설정</h2><span>점수가 아니라 행동 기록·관계 변화·서사 분기로 판정합니다.</span></div><button className="soft-button" onClick={() => updateDraft({ endings: [...draft.endings, { name: '새 결말', description: '사용자에게 보여줄 서사적 결과를 작성하세요.', condition: '어떤 플레이에서 나오는 결말인지 자연어로 작성하세요.' }] })}>＋ 결말 추가</button></div><div className="ending-grid">{draft.endings.map((ending, index) => <article className="ending-edit-card" key={`${mode}-ending-${index}`}><div><span>{index + 1}</span><button type="button">•••</button></div><Field label="결말 이름"><input value={ending.name} onChange={(event) => updateEnding(index, { name: event.target.value })} /></Field><Field label="결말 설명"><textarea rows={4} value={ending.description} onChange={(event) => updateEnding(index, { description: event.target.value })} /></Field><Field label="어떤 플레이에서 나오는 결말인지"><textarea rows={3} value={ending.condition} onChange={(event) => updateEnding(index, { condition: event.target.value })} /></Field><small>AI가 사용자 발화와 행동 기록을 분석해 세부 조건을 생성합니다.</small></article>)}</div></section>}
        {section === 'assets' && <section className="builder-block"><div className="block-heading"><div><h2>배경 이미지</h2><span>캐릭터와 배경을 분리해 장면마다 재사용합니다.</span></div><button className="soft-button">＋ 배경 등록</button></div><div className="asset-library"><article className="selected"><div className="asset-scene convenience" /><strong>{draft.background}</strong><small>현재 시나리오에서 사용 중</small><button>선택됨</button></article><article><div className="asset-scene clubroom" /><strong>대학교 동아리방</strong><small>1920 × 1080</small><button>선택</button></article><article><div className="asset-scene street" /><strong>식당 앞 거리</strong><small>1920 × 1080</small><button>선택</button></article><button className="asset-upload"><span>＋</span><strong>새 배경 업로드</strong><small>캐릭터 없이 배경만 등록</small></button></div><div className="asset-policy"><strong>등록 구조</strong><div><span>캐릭터 레이어</span><i>＋</i><span>배경 레이어</span><i>→</i><span>자동 합성 미리보기</span></div><p>소품을 별도 자산으로 받지 않습니다. 특정 물건이 반드시 필요한 장면은 배경 이미지 안에 포함하거나 화면 해설로 표현합니다.</p></div></section>}
        {section === 'rules' && <section className="builder-block"><div className="block-heading"><div><h2>AI 자동 생성 규칙</h2><span>제작자가 모든 사용자 답변 분기를 직접 작성하지 않아도 됩니다.</span></div><button className="soft-button">자동 생성 다시 실행</button></div><div className="rule-layout"><article><h3>사용자 응답 유형</h3>{['명확한 선택 + 이유 설명', '명확한 선택', '결정을 미룸 / 회피', '캐릭터에게 질문함', '농담이나 엉뚱한 응답', '맥락과 맞지 않는 응답'].map((item, index) => <div className={`rule-line level-${index < 2 ? 'good' : index < 4 ? 'mid' : 'warn'}`} key={item}><i />{item}<span>{index < 2 ? '적합' : index < 4 ? '확인' : '주의'}</span></div>)}</article><article><h3>관찰 항목</h3>{['선택 명확성', '근거 설명', '상대 발화 고려', '맥락 적합성'].map((item) => <div className="weight-row" key={item}><span>{item}</span><i><b style={{ width: `${55 + item.length * 6}%` }} /></i></div>)}<small>사용자 결과 화면에는 숫자 점수를 노출하지 않습니다.</small></article><article><h3>관계 변화 규칙</h3><div className="relation-rule positive"><span>＋</span><div><strong>솔직한 자기표현</strong><small>캐릭터 성향에 따라 관계 변화</small></div></div><div className="relation-rule positive"><span>＋</span><div><strong>상대 상황을 확인함</strong><small>신뢰와 편안함에 반영</small></div></div><div className="relation-rule negative"><span>−</span><div><strong>결정이나 책임을 반복 회피</strong><small>현재 시나리오의 진행에만 반영</small></div></div></article></div></section>}
        {section === 'preview' && <section className="builder-block preview-block"><div className="block-heading"><div><h2>시나리오 미리보기</h2><span>실제 웹 플레이 화면과 동일하게 캐릭터는 중앙, 화면 해설과 대사는 하단에 표시됩니다.</span></div></div><div className="preview-stage"><div className={`preview-scene mode-visual-${mode.toLowerCase()}`}><div className="preview-avatars">{activeCharacters.map((character, index) => <PersonAvatar key={character.id} name={character.name} accent={['violet', 'blue', 'mint'][index % 3]} large />)}</div><div className="preview-caption"><span>{draft.turns[0]?.situation}</span><strong>{draft.turns[0]?.line}</strong></div></div><div className="always-on-preview"><span className="listening-dot" /><div><strong>음성 자동 인식 중</strong><small>사용자가 말하면 별도 버튼 없이 자동으로 자막에 반영됩니다.</small></div><div className="mini-wave"><i /><i /><i /><i /></div></div><div className="preview-goal"><strong>이번 턴에서 사용자가 할 행동</strong><p>{draft.turns[0]?.userGoal}</p></div></div></section>}
      </main>
      <aside className="builder-inspector"><section><div className="inspector-title"><strong>✦ AI 자동 생성 요약</strong><button>수정하기</button></div><h3>사용자 응답 유형</h3>{['명확한 선택 + 이유 설명', '명확한 선택', '결정을 미룸 / 회피', '캐릭터에게 질문함', '농담 / 엉뚱한 대답', '맥락과 맞지 않는 대답'].map((item, index) => <div className="inspector-line" key={item}><i className={index < 2 ? 'green' : index < 4 ? 'yellow' : 'red'} />{item}</div>)}</section>{mode !== 'C' && <section><h3>최신 결과 정책</h3><ul><li>숫자 점수·그래프를 노출하지 않음</li><li>실제 발화 근거를 인용·요약</li><li>효과적이었던 부분 1~2개</li><li>명확할 때만 놓친 부분 1개</li><li>다른 결말 조건이나 공략 힌트 없음</li></ul></section>}{mode === 'C' && <section><h3>C 모드 참여 구조</h3><ul><li>캐릭터 {activeCharacters.length}명 설정</li><li>대표 화자: {activeCharacters.find((character) => character.id === leadCharacterIds.C)?.name ?? activeCharacters[0]?.name}</li><li>공통 시작 장면 1개</li><li>다른 캐릭터는 순차 참여</li></ul></section>}<section><h3>장면 구성</h3><div className="layer-summary"><span>배경</span><b>＋</b><span>캐릭터</span></div><p>별도 소품 등록 없이 두 레이어만 사용합니다.</p></section><button type="button" className="inspector-preview" onClick={() => setSection('preview')}>이 턴 미리보기</button></aside>
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
  const goals = scenario.id === 'snack'
    ? ['짧은 시간 안에 하나를 선택하기', '선택한 이유를 자기 말로 설명하기', '상대 취향과 달라도 결정을 유지하기']
    : scenario.id === 'lunch'
      ? ['전달받은 여러 의견을 정리하기', '원하는 것과 할 수 없는 조건을 함께 확인하기', '실행 가능한 최종안을 제안하기']
      : ['내 이야기부터 할지 캐릭터 이야기를 들을지 선택하기', '부담이 낮은 일상 질문부터 천천히 참여하기', '평가 없이 원하는 속도로 관계를 이어가기']
  return <div className="scenario-intro-page"><header className="simple-header"><Logo /><button type="button" className="outline-button" onClick={onBack}>시나리오 목록</button></header><main className="intro-content"><div className="intro-breadcrumb"><ModeBadge mode={scenario.mode} /><span>{scenario.duration}</span></div><h1>{scenario.title}</h1><p className="intro-summary">{scenario.summary}</p><section className="intro-layout"><div className="intro-main"><section><span className="intro-label">이번 시나리오에서 해볼 것</span><ul>{goals.map((goal) => <li key={goal}><span>✓</span>{goal}</li>)}</ul></section><section><span className="intro-label">진행 방식</span><div className="process-row"><div><b>1</b><strong>장면 확인</strong><small>화면 해설과 캐릭터 대화</small></div><i>→</i><div><b>2</b><strong>자동 음성 인식</strong><small>버튼 없이 말하면 자동 인식</small></div><i>→</i><div><b>3</b><strong>{scenario.mode === 'C' ? '자유 대화' : '결말과 피드백'}</strong><small>{scenario.mode === 'C' ? '평가 없이 이어가기' : '실제 발화 근거로 설명'}</small></div></div></section>{endingCount > 0 && <section><div className="locked-heading"><div><span className="intro-label">발견할 수 있는 결말</span><p>결말의 이름과 조건은 시작 전에 공개하지 않습니다.</p></div><strong>총 {endingCount}개</strong></div><div className="locked-ending-row">{Array.from({ length: endingCount }).map((_, index) => <div key={index}><span>▣</span><strong>잠긴 결말 {index + 1}</strong><small>플레이 후 발견</small></div>)}</div></section>}</div><aside className="intro-side"><span className="intro-label">등장 캐릭터</span><div className="intro-characters">{scenario.characterNames.map((name, index) => <div key={name}><PersonAvatar name={name} accent={['violet', 'blue', 'mint'][index]} large /><strong>{name}</strong>{scenario.mode === 'C' && index === 0 && <small>대표 화자</small>}</div>)}</div><div className="intro-notice"><strong>시작하기 전에</strong><p>마이크 권한을 허용하면 대화 중 별도 버튼을 누르지 않아도 음성을 자동으로 인식합니다. 언제든 키보드로 대신 입력할 수 있습니다.</p></div><button type="button" className="primary-button intro-start" onClick={onStart}>{scenario.mode === 'C' ? '대화 시작하기' : '시나리오 시작하기'} →</button></aside></section></main></div>
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
    speaker: '점장',
    line: '지금까지 고른 기준이 꽤 구체적이네요. 가격, 용량, 취향을 모두 고려하면 어떤 상품을 추천하시겠어요?',
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
  const [reply, setReply] = useState<{ speaker: string; line: string; advance: boolean } | null>(null)
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
        else setReply({ speaker: '하루', line: '안 돼. 오늘은 네 선택 연습이잖아. 다시. 매운맛, 치즈맛, 하나.', advance: false })
        return
      }
      if (asksBack) {
        const nextRecords = [...answers, { turn, text: value, hasReason: true }]
        setAnswers(nextRecords)
        setReply({ speaker: '하루', line: '먹고 나면 정신이 번쩍 들어서. 자, 내 이야기는 했으니까 이제 네 선택.', advance: false })
        return
      }
      const choseSpicy = value.includes('매운')
      const choseCheese = value.includes('치즈')
      if (!choseSpicy && !choseCheese) {
        setReply({ speaker: '안내', line: '매운맛 또는 치즈맛 중 하나를 먼저 말한 뒤 이유를 덧붙여 주세요.', advance: false })
        return
      }
      const nextRecords = [...answers, { turn, text: value, hasReason: hasReason(value) }]
      setAnswers(nextRecords)
      setReply({ speaker: '하루', line: choseSpicy ? '역시. 오늘은 좀 화끈하게 가야지. 너, 생각보다 결단력 있네?' : '치즈맛이라고? 넌 핫한 사람인 줄 알았는데 조금 실망이야. 그래도 취향이 다르면 한 봉지씩 살 수 있으니까 나쁘진 않네.', advance: true })
      return
    }
    const nextRecords = [...answers, { turn, text: value, hasReason: hasReason(value) }]
    setAnswers(nextRecords)
    if (turn >= snackScenarioRounds.length - 1) finishWithEnding(nextRecords, avoidanceCount)
    else setReply({ speaker: '선택 기록', line: '선택과 이유가 기록되었습니다. 다음 비교로 넘어갑니다.', advance: true })
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
  const activeSpeaker = reply?.speaker ?? round.speaker
  const activeLine = reply?.line ?? round.line
  return <div className="runner-page snack-scenario-page">
    <header className="runner-header"><button type="button" className="back-button" onClick={onExit}>←</button><div><ModeBadge mode="A" /><strong>{scenario.title}</strong><span className="documented-badge">기획서 A-1 목업</span></div><div className="runner-progress"><span>{turn + 1} / {snackScenarioRounds.length}턴</span><i><b style={{ width: `${((turn + 1) / snackScenarioRounds.length) * 100}%` }} /></i></div><button type="button" className="outline-button" onClick={onExit}>나가기</button></header>
    <main className="scene-stage stage-snack-art"><div className="scene-dialogue-bar"><div className="scene-narration">{round.narration}</div><div className="speaker-area"><article className="speech-card"><PersonAvatar name={activeSpeaker} accent={activeSpeaker === '점장' ? 'blue' : 'violet'} /><div><span>{activeSpeaker}</span><p>{activeLine}</p></div></article></div></div></main>
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

function ResultPage({ result, onRestart, onList }: { result: ResultData; onRestart: () => void; onList: () => void }) {
  const hiddenEndingCount = result.scenario.id === 'snack' ? 3 : result.scenario.id === 'lunch' ? 2 : 0
  return <div className="result-page"><header className="result-header"><Logo /><div><ModeBadge mode={result.scenario.mode} /><span>{result.scenario.title}</span></div><button type="button" className="outline-button" onClick={onList}>시나리오 목록</button></header><main className="result-content"><section className="ending-hero"><span>내가 도달한 결말</span><h1>{result.ending}</h1><p>{result.story}</p></section><section className="reason-card"><span>왜 이런 결말이 나왔을까요?</span><p>{result.reason}</p></section><div className="feedback-layout"><div><section className="feedback-card effective"><div className="feedback-label"><span>✓</span>이번 대화에서 효과적이었던 부분</div><ul>{result.effective.map((item) => <li key={item}>{item}</li>)}</ul><blockquote>“{result.evidence}”</blockquote></section>{result.missed && <section className="feedback-card missed"><div className="feedback-label"><span>!</span>한 번 더 생각해볼 부분</div><p>{result.missed}</p></section>}<section className="feedback-card remember"><div className="feedback-label"><span>→</span>다음에 비슷한 상황이 온다면</div><p>{result.remember}</p></section></div><aside><section className="feedback-card reaction"><span>캐릭터의 마지막 반응</span><p>{result.reaction}</p><div>{result.relation}</div></section></aside></div>{hiddenEndingCount > 0 && <section className="discovered-endings"><div><span>다른 이야기의 가능성</span><h2>아직 발견하지 않은 결말이 {hiddenEndingCount}개 있어요</h2><p>결말의 이름과 조건은 공개하지 않습니다. 다른 방식으로 대화하면 새로운 결과를 발견할 수 있습니다.</p></div><div className="locked-result-grid">{Array.from({ length: hiddenEndingCount }).map((_, index) => <article key={index}><span>▣</span><strong>잠긴 결말</strong><small>조건 비공개</small></article>)}</div></section>}<div className="result-actions"><button type="button" className="primary-button" onClick={onRestart}>처음부터 다시 하기</button><button type="button" className="outline-button" onClick={onList}>다른 시나리오 보기</button></div></main></div>
}

function App() {
  const [page, setPage] = useState<Page>('home')
  const [characters, setCharacters] = useState<Character[]>(initialCharacters)
  const [scenarios] = useState<Scenario[]>(initialScenarios)
  const [editingCharacter, setEditingCharacter] = useState<Character | null>(null)
  const [runningScenario, setRunningScenario] = useState<Scenario | null>(null)
  const [result, setResult] = useState<ResultData | null>(null)
  const [toast, setToast] = useState('')
  const run = (scenario: Scenario) => { setRunningScenario(scenario); setResult(null); setPage('intro') }
  const navigate = (next: Page) => { setPage(next); setResult(null); setRunningScenario(null) }
  const saveCharacter = (character: Character) => { setCharacters((current) => current.some((item) => item.id === character.id) ? current.map((item) => item.id === character.id ? character : item) : [character, ...current]); setToast(`${character.name} 설정을 저장했습니다.`); navigate('characters') }
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
    return runningScenario.id === 'snack' ? <SnackSelectionScenario {...runnerProps} /> : <ScenarioRunner {...runnerProps} />
  }
  if (page === 'result' && result) return <ResultPage result={result} onRestart={() => { setResult(null); setRunningScenario(result.scenario); setPage('run') }} onList={() => navigate('scenarios')} />
  return <div className="web-app">{shellVisible && <Sidebar page={page} onNavigate={navigate} />}<div className="main-shell">{shellVisible && <TopHeader page={page} onNavigate={navigate} />}<main className="page-scroll">{content}</main></div>{toast && <button type="button" className="toast" onClick={() => setToast('')}><span>✓</span>{toast}</button>}</div>
}

export default App
