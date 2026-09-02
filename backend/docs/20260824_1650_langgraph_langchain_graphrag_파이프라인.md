# LangGraph·LangChain·부분 GraphRAG 파이프라인

작성 시각: 2026-08-24 16:50 KST

## 현재 요청 처리 흐름

```text
사용자 메시지
  -> LangGraph: select_speakers
  -> LangGraph: retrieve_primary_context
       -> LangChain Runnable
       -> 일반 메모리 검색 (기존 memory_acl 권한 검사)
       -> 관계 질문일 때만 GraphRAG edge 검색 (동일한 memory_acl 재검사)
  -> LangGraph: generate_primary
  -> LangGraph: store_primary_memory
       -> 새 기억이 관계를 명시하면 memory_graph_edges에 edge 저장
  -> 조건 분기
       -> 필요 없음: finalize
       -> 필요함: retrieve_secondary_context -> generate_secondary -> store_secondary_memory -> finalize
```

## 구성 요소와 책임

- `ConversationService`: HTTP 요청 검증, 메시지/ScenePlan 저장, 응답 조립. 대화 순서를 직접 제어하지 않고 LangGraph를 호출한다.
- `ConversationWorkflow`: 발화자 선택·검색·생성·기억 저장·조건 분기를 독립 노드로 실행한다. 노드별 처리 시간이 `workflow_node_duration_ms{engine="langgraph"}`에 기록된다.
- `LangChainMemoryGraphRetriever`: 기존 메모리 저장소를 LangChain `Runnable`과 `Document`로 감싼 검색 어댑터다. 나중에 임베딩 기반 retriever로 바꿔도 대화 그래프 노드를 바꾸지 않도록 경계를 분리한다.
- `memory_graph_edges`: 새로 저장된 기억에서 명시적으로 추출한 `주체 - 관계 - 대상` edge를 저장한다.

## GraphRAG의 적용 범위

이 구현은 전체 메모리 검색을 GraphRAG로 대체하지 않는다.

- 일반 대화: 최근 ACL 허용 메모리 검색만 사용한다.
- 관계·이유·전후 맥락 질문: 관계 intent가 감지될 때만 edge를 추가 검색한다.
- 권한: edge 원본 메모리에 대해 해당 캐릭터의 `memory_acl.can_read=true`가 확인될 때만 반환한다.
- 데이터 축적: 배포 이후 새로 저장되는 기억부터 edge가 생성된다. 기존 `memory_items`는 자동으로 재가공하지 않는다.

## 배포 전 필수 실행

애플리케이션을 새 코드로 실행하기 전에 데이터베이스에 다음 migration을 적용해야 한다.

```powershell
cd backend
alembic upgrade head
```

이 migration은 `memory_graph_edges` 테이블과 인덱스만 추가한다. 기존 메모리와 ACL을 변경하거나 삭제하지 않는다.

## 관측성에서 확인할 값

- `conversation_workflows_total{engine="langgraph"}`: 워크플로 성공·실패 수
- `workflow_node_duration_ms{engine="langgraph"}`: 선택, 검색, 생성, 저장, 종료 노드별 시간
- `memory_search_result_count`: 일반 ACL 메모리 검색 결과 수
- `graphrag_search_result_count`: 관계 edge 검색 결과 수
- `conversation_execution_paths_total{engine="langgraph"}`: primary / primary_secondary 경로 비율

## 아직 의도적으로 하지 않은 것

- pgvector 임베딩 검색: embedding 모델·차원·재색인 정책이 확정되지 않아 이번 변경에는 넣지 않았다.
- LangGraph durable checkpoint: `Job`/`JobCheckpoint`은 삭제 보류이며, 실제 worker 도입 시 함께 연결한다.
- 자동 Tool Calling: 외부 검색, 캘린더, DB 변경처럼 모델이 선택해야 하는 도구가 확정되지 않아 도입하지 않았다.

