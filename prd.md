# PRD: RF Emitter Tracker — Heatmap Viewer (React)

- 문서 상태; v1.0 (2026-10-11)
- 대상 구현자; VS Code의 Claude Code
- 관련 시스템; Toy EW(ES) prototype, Pi hub (`hub.py`), Lucas EKF tracker (`rssi_only_v2.py`)

---

## 1. 배경

- 4개의 RSSI 센서 노드(Raspberry Pi 3B, NU-87 TinyDK ×2, Arduino UNO Q)가 1 m × 1 m 정사각형 모서리에 배치되어 Wi-Fi 송신원(`DRONE-01`)의 RSSI를 측정한다.
- Pi의 `hub.py`가 노드 데이터를 모아 likelihood heatmap과 EKF(constant velocity) 추적 결과를 계산하고, **WebSocket으로 1 Hz broadcast**한다.
- 이 PRD의 범위는 그 frame을 **구독만 하여** 노트북 browser에 시각화하는 React app이다.

## 2. 목표

1. Pi가 publish하는 frame을 실시간으로 받아 heatmap, 노드 상태, Kalman 추적을 한 화면에 표시한다.
2. 데모 중 네트워크 끊김, 노드 down, Kalman 초기화 전 상태에서도 화면이 깨지지 않는다.
3. Pi 없이도 개발과 데모 리허설이 가능하도록 **mock mode**를 제공한다.

## 3. 범위 밖 (Non-goals)

- Server에 요청을 보내는 기능 (명령, 설정 변경 등). Viewer는 **read-only subscriber**이다.
- 위치 추정 계산. 모든 추정은 Pi에서 끝난 상태로 온다; viewer는 표시만 한다.
- 인증, 다중 사용자, 녹화 저장 (향후 고려).
- SLM 예측 생성. `slm` 필드는 표시 slot만 준비한다.

---

## 4. 시스템 인터페이스

### 4.1 연결

- Protocol; WebSocket, text frame, JSON 1개 = message 1개.
- 기본 URL; `ws://<Pi Tailscale IP>:8765`
- URL 우선순위; query param `?ws=` → env `VITE_WS_URL` → 기본값 `ws://raspberrypi:8765`.
- Client는 연결 후 아무것도 보내지 않는다. Server는 client message를 무시한다.

### 4.2 Frame schema (hub.py 출력 그대로)

```jsonc
{
  "t": 1760140000.123,                 // unix seconds (Pi 시각)
  "nodes": {
    "raspberrypi": { "x": -0.5, "y": -0.5, "rssi": -41.0, "d": 0.62, "fresh": true },
    "nu87a":       { "x":  0.5, "y": -0.5, "rssi": null,  "d": null, "fresh": false }
    // 노드 이름과 개수는 가변. key를 고정으로 가정하지 말 것.
  },
  "grid": {                            // null 가능 (살아있는 노드 0개)
    "x0": -0.6, "y0": -0.6,            // grid 원점 (m), 가장 작은 x, y
    "step": 0.05,                      // 칸 크기 (m)
    "n": 25,                           // n × n
    "v": [[0.0, 0.01, ...], ...]       // v[iy][ix], 0..1 정규화 (max = 1)
  },
  "est": [0.12, -0.05],                // grid argmax 추정, null 가능 (노드 3개 미만)
  "kalman": {
    "state": "track",                  // "init k/K" 문자열이면 아직 초기화 중
    "pos": [0.11, -0.04],              // m
    "vel": [0.02, 0.01],               // m/s
    "cov": [[0.004, 0.0], [0.0, 0.005]], // 위치 2×2 covariance (m²)
    "used": 3                          // 이번 tick에 χ² gate 통과한 측정 수
  },
  "slm": null                          // 향후 { "dx", "dy", "reason" }
}
```

**좌표계 규칙**
- 단위 m, 원점은 정사각형 중심, x 오른쪽 +, y 위쪽 +.
- `grid.v[iy][ix]`의 실제 좌표는 $x = x_0 + ix \cdot step$, $y = y_0 + iy \cdot step$.
- `v[0]`은 **가장 아래쪽 행**(y 최소)이다. Canvas는 y가 아래로 증가하므로 그릴 때 행 순서를 뒤집어야 한다.
- `kalman.state`가 `"init ..."`이면 `pos`, `vel`, `cov`, `used` 필드가 없다.

### 4.3 Parsing 요구사항

- 모든 frame은 runtime validation(예: `zod`)을 거친다. 실패한 frame은 버리고 console에 경고만 남긴다; 화면은 직전 frame을 유지한다.
- 알 수 없는 추가 필드는 무시한다 (forward compatible).

---

## 5. 기능 요구사항

### F1. Map view (핵심)
- 정사각형 canvas, 화면 높이에 맞춰 resize. 표시 범위는 `grid` 범위 (기본 −0.6 ~ 0.6 m).
- **Heatmap layer**; `grid.v`를 sequential colormap(예: viridis 계열)으로 칠한다. 값 0은 투명에 가깝게.
- **Grid/axis layer**; 0.25 m 간격 보조선, 1 m 정사각형 외곽선, 축 라벨(m).
- **Node layer**; 노드 위치에 marker + 이름. `fresh && rssi != null`이면 활성 색, 아니면 회색. 활성 노드는 `d`를 반지름으로 하는 얇은 원(거리 ring)을 그린다.
- **Estimate layer**; `est`를 작은 십자로 표시.
- **Kalman layer**
  - `pos`에 원형 marker.
  - `cov`로 **2σ covariance ellipse**를 그린다 (eigen decomposition; 반축 $2\sqrt{\lambda_i}$, 회전은 고유벡터 각도).
  - `vel` 방향 화살표. 길이는 1초 후 예측 위치 $pos + vel \cdot \Delta t$ ($\Delta t$ = 1 s, 설정 가능)까지.
  - **Trail**; 최근 N개(기본 30) `pos`를 선으로 연결, 오래된 점일수록 투명하게.
- **SLM layer (placeholder)**; `slm`이 non-null이면 `pos`에서 $(dx, dy)$ 방향으로 Kalman 화살표와 다른 색/점선 화살표를 그린다.
- Layer별 on/off toggle (heatmap, rings, est, ellipse, trail, prediction).

### F2. Status panel
- 연결 상태; `connecting`, `live`, `stale`(마지막 frame 후 3초 초과), `disconnected`.
- 마지막 frame 시각과 frame 수신 간격.
- Kalman 상태; `init k/K` 진행 표시 또는 `track` + `used/전체 노드 수`.
- 노드 표; 이름, RSSI(dBm), 거리(m), fresh 여부. (UI는 list 형태로 구현해도 됨.)
- 추정 위치 수치; est, kalman pos, speed $\lVert vel \rVert$ (m/s), heading(°).

### F3. 연결 관리
- 끊기면 exponential backoff로 자동 재연결 (0.5 s 시작, 최대 5 s).
- 재연결 시 trail은 유지하되, 끊긴 구간은 선으로 잇지 않는다.
- URL 입력란 제공; 변경 시 즉시 재연결, `localStorage`에 저장 (try/catch).

### F4. Mock mode
- `?mock=1` 또는 UI toggle로 활성화.
- 내장 generator가 4.2 schema와 **동일한 frame**을 1 Hz로 생성한다: 4개 노드, 원 궤적 표적 (반지름 0.3 m), RSSI model $RSSI = A_0 - 10n\log_{10}(d) + \mathcal{N}(0, 2^2)$, $A_0 = -34.5$, $n = 2.5$.
- Kalman 값은 mock에서 단순 low-pass + 차분 속도로 흉내만 내도 된다.
- 처음 5 frame은 `kalman.state = "init k/5"`로 보내서 초기화 UI를 검증한다.
- 랜덤으로 노드 하나를 몇 초간 `fresh:false`로 만들어 down 처리 UI를 검증한다.

### F5. Pause / replay (선택, P2)
- Pause 버튼; 수신은 계속하되 화면 갱신만 멈춤.
- 최근 120 frame ring buffer, slider로 되감기.

---

## 6. 비기능 요구사항

- **Stack**; Vite + React 18 + TypeScript. 상태 관리는 React state 또는 `zustand` 정도로 가볍게. Rendering은 HTML `<canvas>` 2D (외부 chart library 불필요).
- **성능**; frame 1 Hz, grid 25×25 기준. Frame 사이에는 Kalman marker를 `requestAnimationFrame`으로 예측 위치 쪽으로 부드럽게 보간해도 된다 (P2). 60 fps에서 CPU 사용을 낮게 유지.
- **Robustness**; 어떤 필드가 null이어도 crash 금지. Error boundary 적용.
- **Theme**; 어두운 배경 기본 (데모 조명 대비). 색만으로 의미를 전달하지 않는다 (marker 모양도 구분).
- **배포**; `npm run dev`(개발), `npm run build` 후 static 파일. 외부 CDN 의존 없이 offline 동작 (해커톤 네트워크 불안정 대비).

---

## 7. 권장 구조

```
viewer/
  src/
    types/frame.ts        // zod schema + TS type
    ws/useFrameStream.ts  // 연결, 재연결, stale 판정, mock 전환
    mock/generator.ts     // F4
    map/
      MapCanvas.tsx       // layer 합성
      layers/heatmap.ts
      layers/nodes.ts
      layers/kalman.ts    // ellipse, arrow, trail
      transform.ts        // world(m) <-> canvas(px), y 뒤집기
    math/ellipse.ts       // 2×2 eigen decomposition
    panel/StatusPanel.tsx
    App.tsx
  scripts/mock-server.mjs // ws 패키지로 mock frame을 :8765에 broadcast (Pi 대역)
```

- `scripts/mock-server.mjs`는 browser 내장 mock과 별개로, **실제 WebSocket 경로**까지 검증하기 위한 것이다.

---

## 8. 수용 기준 (Acceptance criteria)

1. `npm run dev` + `?mock=1`로 열면 heatmap, 노드 4개, 원을 그리며 움직이는 Kalman marker, ellipse, 속도 화살표, trail이 보인다.
2. `node scripts/mock-server.mjs` 실행 후 `?ws=ws://localhost:8765`로 접속하면 1과 같은 화면이 나온다.
3. Mock server를 종료하면 3초 안에 `stale` → `disconnected`로 바뀌고, 다시 켜면 자동으로 `live`로 돌아온다.
4. `kalman.state = "init 2/5"` frame에서 Kalman layer는 숨겨지고 panel에 진행도가 표시된다.
5. `grid: null`, `est: null`, 노드 전부 `fresh:false`인 frame에서도 crash 없이 빈 map과 경고 상태를 보여준다.
6. 좌표 검증; mock 표적이 $(0.3, 0)$일 때 marker가 화면 중심의 **오른쪽**, $(0, 0.3)$일 때 **위쪽**에 표시된다.
7. `math/ellipse.ts` unit test; 대각 cov, 회전된 cov(45°), 특이 cov(determinant ≈ 0)에서 올바른 반축/각도를 반환하고 NaN이 없다.
8. 실제 Pi `hub.py`에 연결했을 때 코드 수정 없이 동작한다.

---

## 9. 우선순위

- **P0**; 4.2 schema parsing, F1 heatmap/node/kalman marker, F2 연결 상태, F3 재연결, F4 mock.
- **P1**; covariance ellipse, 속도 화살표, trail, layer toggle, mock-server script.
- **P2**; frame 사이 보간, F5 pause/replay, SLM 화살표.

## 10. 미해결 사항

- 향후 UNO Q가 publisher가 되면 URL만 바꾼다; schema는 동일하게 유지하기로 합의됨.
- `slm` 필드의 최종 형식 (`dx, dy`가 m 단위 변위인지 m/s 속도인지)은 UNO Q 단계에서 확정한다. 현재는 m 단위 변위로 가정한다.
- 장기 목표인 holographic sight overlay는 이 viewer의 rendering layer를 재사용할 수 있도록 layer 함수를 React와 분리해 둔다 (`layers/*.ts`는 순수 canvas 함수).