# NJIAKIKOBA

Jukwaa la akiba, mikopo na usimamizi wa vikundi (Tanzania).

## Vipengele muhimu

- Vikundi vingi; kila kikundi ukomo wa wanachama 999 (developer anaweza kuongeza)
- Registration code ya kikundi: `NK/{INITIALS}` (mfano CHAPAKAZI → `NK/CK`)
- Namba ya mwanachama: `NK/{INITIALS}-####` (mfano `NK/CK-0012`)
- Ada ya mfumo: **2%** kila muamala + **1%** amana ya kwanza → inatumwa kwenye `DEVELOPER_LIPA_NUMBER`
- WebAuthn (fingerprint/Face ID) kwa usajili wa viongozi
- Group chat, conference call (Jitsi), cheti, risiti
- Developer Room + Support Desk

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Jaza SECRET_KEY, DEVELOPER_PASSWORD_HASH, DEVELOPER_LIPA_NUMBER, BLMPAY_*
export $(grep -v '^#' .env | xargs)
python app.py
```

Production (Render / VPS):

```bash
gunicorn -b 0.0.0.0:$PORT app:app
```

## Environment muhimu

| Variable | Maelezo |
|----------|---------|
| `DEVELOPER_LIPA_NUMBER` | Namba inayopokea ada 2% + 1% (mfano 2557…) |
| `BLMPAY_API_KEY` | API key ya gateway |
| `BLMPAY_WEBHOOK_URL` | `https://domain/webhooks/blmpay` |
| `BLMPAY_WEBHOOK_SECRET` | Saini ya webhook |
| `DEVELOPER_PASSWORD_HASH` | Hash ya nenosiri la Developer Room |

## Muundo wa folders

```
njiakikoba/
  app.py
  requirements.txt
  .env.example
  README.md
  templates/
  static/
```

## Lugha

SW / EN kupitia `/set-lang/sw` na `/set-lang/en` (session).
