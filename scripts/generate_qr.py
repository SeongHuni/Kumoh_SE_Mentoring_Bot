"""발표 당일 현장에서 실행: 현재 와이파이 IP를 자동으로 찾아 접속 QR을 새로 만든다.

    python scripts/generate_qr.py            # 기본 포트 8080
    python scripts/generate_qr.py --port 8080

netsh portproxy 는 listenaddress=0.0.0.0 이라 IP가 바뀌어도 다시 설정할 필요 없다.
바뀌는 건 QR/URL에 박히는 IP뿐이므로, 이 스크립트만 다시 돌리면 된다.
"""
import argparse
import socket
import urllib.request

import qrcode


def detect_lan_ip() -> str:
    # 실제 패킷을 보내지 않고 OS 라우팅 테이블만 이용해 "밖으로 나갈 때 쓰는 인터페이스의 IP"를 얻는다.
    # 이 방식이 Docker/WSL 가상 어댑터가 아니라 실제 와이파이 어댑터의 IP를 집어준다.
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def check_reachable(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--out", default="docs/챗봇_접속_QR.png")
    args = parser.parse_args()

    ip = detect_lan_ip()
    url = f"http://{ip}:{args.port}"

    reachable = check_reachable(url)

    img = qrcode.make(url, box_size=12, border=4)
    img.save(args.out)

    print(f"IP:     {ip}")
    print(f"URL:    {url}")
    print(f"접속:   {'정상 (200 OK)' if reachable else '!!실패 - 서비스/포트포워딩 확인 필요!!'}")
    print(f"QR 저장: {args.out}")


if __name__ == "__main__":
    main()
