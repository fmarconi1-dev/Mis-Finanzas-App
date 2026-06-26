# Deploy a Oracle Cloud + Cloudflare Tunnel

Guía paso-a-paso para llevar Mis Finanzas a producción.

Estrategia:
- VM **Always Free Ampere ARM** de Oracle Cloud (gratis para siempre — 4 OCPU, 24 GB RAM).
- App corre en Docker contra un volumen persistente.
- **Cloudflare Tunnel** expone la app sin abrir ningún puerto al internet público.
- **Cloudflare Access** (opcional, gratis hasta 50 usuarios) suma una capa de auth previa con email-code.

---

## Pre-requisitos

1. Cuenta Oracle Cloud: https://www.oracle.com/cloud/free/
2. Cuenta Cloudflare: https://www.cloudflare.com (gratis).
3. Un dominio que ya esté en Cloudflare (transferí el DNS si todavía no, o registrá uno baratito).

---

## Parte 1 — VM Always Free en Oracle Cloud

1. Consola Oracle → **Compute → Instances → Create Instance**.
2. **Image**: Canonical Ubuntu 22.04.
3. **Shape**: cambiá a "Ampere → VM.Standard.A1.Flex" → 4 OCPU + 24 GB RAM (todo dentro del Always Free).
4. **Networking**: dejá los defaults (subnet pública, VCN nueva). Asigná IP pública.
5. **SSH key**: subí tu clave pública (o generá una nueva y bajá la privada).
6. **Create**.

Anotá la IP pública. Va a ser tu única puerta de entrada por SSH.

### Security list — endurecer

Una vez creada la VM, vas a "Networking → Virtual Cloud Networks → tu VCN → Security Lists → Default Security List":

- **Ingress**: dejá SSH (22) abierto pero idealmente restringido a tu IP de casa (campo "Source CIDR" = `TU_IP/32`).
- **NO abrir 80 ni 443.** Cloudflare Tunnel hace outbound; no necesitamos inbound público.

---

## Parte 2 — Setup del host

```bash
ssh ubuntu@<IP_PUBLICA>

# Update y Docker
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose-plugin curl rsync
sudo usermod -aG docker $USER

# Logout/login para que el grupo docker tome efecto
exit
ssh ubuntu@<IP_PUBLICA>

# Verificar
docker --version
docker compose version
```

---

## Parte 3 — Copiar el código al VM

Desde tu PC (PowerShell o CMD en Windows):

```powershell
# rsync vía WSL/Git Bash, o usando scp directo:
cd "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos"

# Crear destino
ssh ubuntu@<IP_PUBLICA> "mkdir -p ~/finanzas"

# Copiar el código (sin venv, sin data, sin CSVs locales)
scp -r app.py Dockerfile docker-compose.yml requirements.txt .env.example .dockerignore README.md DEPLOY.md core ui scripts ubuntu@<IP_PUBLICA>:~/finanzas/
```

En el VM:

```bash
cd ~/finanzas
cp .env.example .env
nano .env
```

Mínimo en `.env`:

```
DB_PATH=/app/data/finanzas.db
BACKUP_RETENTION=30
```

`FONDO_EMERGENCIA_USD` lo podés editar desde el dashboard una vez logueado, no hace falta acá.

---

## Parte 4 — Migrar tu data local (opcional)

Si querés llevarte la DB con todos tus movimientos:

```powershell
# En tu PC, ASEGURATE de tener Streamlit apagado (Ctrl+C en la terminal local)
cd "C:\Users\Franco\OneDrive\Desktop\Finanzas Personales\App seguimiento de gastos"

ssh ubuntu@<IP_PUBLICA> "mkdir -p ~/finanzas/data/backups"
scp data/finanzas.db ubuntu@<IP_PUBLICA>:~/finanzas/data/
```

Si preferís empezar desde cero en producción, salteá este paso. La primera vez que entres vas a pasar por el onboarding.

---

## Parte 5 — Levantar la app

```bash
cd ~/finanzas
docker compose up -d --build

# Ver que arranque OK
docker compose logs -f
# Ctrl+C para salir del log (el contenedor sigue corriendo)

# Test local
curl http://localhost:8501/_stcore/health
# Devuelve "ok"
```

---

## Parte 6 — Cloudflare Tunnel

### Crear el túnel

1. Cloudflare → tu dominio → **Zero Trust** (menú izquierdo).
2. **Networks → Tunnels → Create a tunnel**.
3. Elegí **Cloudflared**, nombre `mis-finanzas`.
4. Cloudflare te da un comando con un **token**. Copialo entero.

### Instalar cloudflared en el VM

```bash
# ARM64 (la Ampere de Oracle es ARM)
curl -L -o cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb
sudo dpkg -i cloudflared.deb

# Pegá el comando que te dio Cloudflare. Algo así:
sudo cloudflared service install <TU_TOKEN>

# Verificar
sudo systemctl status cloudflared
```

### Mapear el dominio

Volvé a la consola del Tunnel:

1. **Public Hostnames → Add a public hostname**.
2. Subdomain: `finanzas`
3. Domain: `tudominio.com` (debe estar en Cloudflare).
4. Service: `HTTP` → `localhost:8501`.
5. **Save**.

En 30 segundos `https://finanzas.tudominio.com` te lleva al login de la app. HTTPS gratis vía Cloudflare.

---

## Parte 7 — Capa extra de auth (opcional pero recomendado)

Cloudflare Access agrega un email-code antes del login de Streamlit. Útil si vas a compartir la URL con amigos.

1. Cloudflare → **Zero Trust → Access → Applications → Add an application**.
2. Tipo: **Self-hosted**.
3. Application name: `mis-finanzas`.
4. Application domain: `finanzas.tudominio.com`.
5. Identity providers: dejá "One-time PIN" (manda código por mail).
6. Session duration: 24 hours.
7. Next → Policies → Add policy:
   - Name: `usuarios-autorizados`
   - Action: `Allow`
   - Include → Selector: `Emails` → poné los emails que vos y tus amigos van a usar.
8. Save.

Ahora cuando entren a la URL, Cloudflare pide email primero. Si el email está en la lista, manda un código de 6 dígitos. Recién después llegan al login de Streamlit.

---

## Parte 8 — Setear tu primera contraseña

Si copiaste tu DB local, tu usuario `franco` ya tiene contraseña. Si arrancás de cero o cambiaste algo:

```bash
docker compose exec finanzas python -m scripts.setup_password
# Username [local]: franco
# Nueva contraseña: ...
# Repetir: ...
```

---

## Mantenimiento

```bash
# Update código (después de scp de nuevas versiones desde tu PC)
cd ~/finanzas
docker compose up -d --build

# Logs
docker compose logs --tail 100 -f

# Ver estado
docker compose ps

# Restart
docker compose restart

# Detener (sin borrar data)
docker compose down

# Backup manual de la DB
cp data/finanzas.db ~/backups-locales/finanzas-$(date +%Y%m%d).db
```

Los backups automáticos de la app siguen funcionando en `data/backups/` adentro del contenedor (volumen persistente).

---

## Backups remotos (opcional)

La Always Free de Oracle te da 20 GB de Object Storage. Podés sincronizar `data/backups/` diariamente:

```bash
# Instalar OCI CLI (una vez)
sudo apt install -y python3-pip
pip3 install oci-cli
oci setup config

# Crear bucket en Oracle Console → Object Storage → Buckets

# Cron diario a las 3 AM
crontab -e
# Agregar:
0 3 * * * cd ~/finanzas && oci os object bulk-upload --bucket-name mis-finanzas-backups --src-dir data/backups --overwrite
```

Alternativa más simple: Backblaze B2 (10 GB free, API trivial).

---

## Troubleshooting

**`curl: (7) Failed to connect to localhost port 8501`** dentro del VM:
- `docker compose logs` → ver errores de arranque
- `docker compose ps` → verificar que el contenedor esté `healthy`

**Cloudflared no se conecta**:
- `sudo systemctl status cloudflared` → ver logs
- Verificar que el token sea el correcto
- En la consola Cloudflare, el tunnel tiene que aparecer en verde

**Olvidé mi contraseña**:
- `docker compose exec finanzas python -m scripts.setup_password` resetea

**Streamlit muestra "XSRF protection" error**:
- Está habilitado a propósito en el Dockerfile. Si tenés problemas con Cloudflare, agregá esta env var al `docker-compose.yml`:
  ```yaml
  environment:
    - STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false
  ```
  Pero idealmente dejalo `true` y confiá en la auth en cascada (Cloudflare Access + Streamlit-Auth).

---

## Costos

- Oracle Cloud Always Free: **$0** (4 OCPU + 24 GB RAM Ampere ARM, gratis para siempre).
- Cloudflare Tunnel: **$0**.
- Cloudflare Access: **$0** hasta 50 usuarios.
- Object Storage Oracle: **$0** hasta 20 GB.
- Total: **$0/mes** sostenido. Sólo pagás el dominio (~$10/año).

---

## Verificación final

Después del deploy, smoke test:

1. `https://finanzas.tudominio.com` → login screen.
2. Crear cuenta de prueba → onboarding (saldo + fondo USD) → dashboard vacío.
3. Cargar 1 transacción → ver que aparezca en Diario y se actualice Saldo CC.
4. Logout → entrar como `franco` → ver toda tu data intacta.
5. Confirmar aislamiento: cuenta de prueba no ve tus datos, vos no ves los de la cuenta de prueba.

Si los 5 pasos andan, ya está deployado y multi-tenant funcionando.
