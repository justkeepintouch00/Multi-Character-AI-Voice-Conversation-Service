# Frontend

React 19, TypeScript, Vite로 구성된 사용자 화면이다.

## 최초 설치

```powershell
cd frontend
npm install
```

## 개발 서버 실행

```powershell
npm run dev
```

브라우저: <http://127.0.0.1:5173>

FastAPI는 별도 터미널에서 `127.0.0.1:8000`으로 실행해야 한다.

## 검사

```powershell
npm run lint
npm run build
```

## 폴더 역할

```text
frontend/
├─ public/          그대로 배포되는 이미지·아이콘
├─ src/
│  ├─ App.tsx       메인 화면 컴포넌트
│  ├─ App.css       App 화면 스타일
│  ├─ index.css     전역 스타일
│  └─ main.tsx      React 시작점
├─ index.html       Vite HTML 시작 파일
├─ package.json     npm 명령·라이브러리
└─ vite.config.ts   Vite 설정
```

서버 종료: `Ctrl+C`
