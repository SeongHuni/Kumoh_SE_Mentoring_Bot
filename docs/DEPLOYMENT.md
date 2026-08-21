# 배포

## 운영 구성

`compose.production.yaml`은 한 개의 공개 진입점만 엽니다.

```text
브라우저 -> Caddy (80/443) -> Next.js
                         -> /api/* -> FastAPI -> Chroma DB
```

브라우저는 같은 주소의 `/api`로 요청하므로, 방문자의 `localhost:8000`으로 잘못 연결되지 않습니다. FastAPI 포트 8000과 Next.js 포트 3000은 호스트에 직접 공개하지 않습니다.

## 교내 Wi-Fi 한정 배포

1. 학교 전산팀에 **학생이 교내 Wi-Fi에서 외부 인터넷으로 나갈 때 사용하는 공인 IPv4 CIDR 목록**을 요청합니다. 사설 주소(예: `10.x.x.x`)가 아니라 서버가 실제로 확인하는 공인 출발지 주소가 필요합니다.
2. VM 또는 학교 서버의 방화벽에서 TCP `80`, `443`의 **출발지**를 그 CIDR들로만 허용합니다. SSH(22)는 관리자의 개인 IP만 별도로 허용합니다.
3. 서버의 프로젝트 폴더에 실제 `.env`를 만들고 다음 값을 추가합니다.

   ```dotenv
   # 교내 IP로 바로 시험할 때. HTTPS 도메인을 연결하면 도메인만 적습니다.
   SITE_ADDRESS=http://VM_IP
   HTTP_PORT=80
   HTTPS_PORT=443

   # OpenAI 모드에서만 실제 키를 설정합니다. 키는 저장소에 넣지 않습니다.
   OPENAI_API_KEY=
   ```

4. 현재 운영 중인 Chroma 인덱스 전체를 서버의 `chroma_db/`로 복사합니다. 현재 `data/raw/posts.json`의 46개 게시글로 `index --reset`을 실행하면 운영 인덱스 범위가 줄어듭니다.
5. 서버에서 실행합니다.

   ```bash
   docker compose -f compose.production.yaml up -d --build
   docker compose -f compose.production.yaml ps
   ```

6. 교내 Wi-Fi에서 `http://VM_IP/api/health`를 확인하고, 휴대폰 모바일 데이터나 집 인터넷에서는 접속이 거절되는지 확인합니다.

`SITE_ADDRESS`에 실제 도메인(예: `mentor.example.ac.kr`)을 넣으면 Caddy가 HTTPS 인증서를 자동으로 관리합니다. 도메인 없이 내부 IP를 쓰는 첫 시험은 위처럼 `http://`를 명시합니다.

## 공개 배포로 전환

같은 서버에서 방화벽의 출발지를 `0.0.0.0/0`으로 바꾸고, `SITE_ADDRESS`를 HTTPS가 가능한 도메인으로 설정하면 됩니다. 이때는 요청 횟수 제한, API 사용량 알림, 주기적인 Chroma 백업을 추가한 뒤 공개합니다.

## 무료 VM 선택 시 주의점

Chroma DB는 디스크에 유지되어야 합니다. 파일 시스템이 재시작마다 사라지는 무료 웹 호스팅은 이 프로젝트의 운영용으로 쓰지 않습니다. 무료 VM을 선택했다면 인덱스와 `.env`를 백업하고, 해당 서비스의 무료 한도와 회수 정책을 정기적으로 확인합니다.
