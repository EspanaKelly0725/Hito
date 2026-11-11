# CLAUDE.md — Hito

Contexto para cualquier agente que trabaje en este repositorio.

## Qué es Hito

Agente de *contrato a caja* para freelancers: lee el contrato, factura cada hito
por PayPal, estima la probabilidad de no pago con un modelo de riesgo propio,
cobra con el tono que esa probabilidad merece y reparte lo que entra entre los
colaboradores. Backend Python/FastAPI + SQLite, agentes sobre un modelo **de código abierto
corriendo en local** (Qwen2.5 3B Instruct, Apache-2.0, vía Ollama) con Claude
como motor opcional, y pasarela PayPal real (Invoicing v2, Payouts v1,
Webhooks) con una implementación *mock* equivalente para que se pueda ejecutar
sin cuentas.

- Todo lo que decide un agente se escribe en `events` con `actor='agent'`; todo
  lo que decide la persona, con `actor='human'`. Esa tabla es la bitácora de
  auditoría y se muestra en el panel. No rompas esa convención.
- Los montos **nunca** los calcula el modelo. La aritmética va en Python
  (`app/agents/splitter.py`, `Decimal`); el modelo solo escribe el texto.
- `app/agents/*` tienen todos un *fallback* determinista con el mismo contrato de
  salida. Si añades un agente, añade su fallback: la demo no puede depender de
  que haya un modelo disponible.
- El motor por defecto es local y gratuito a propósito: un contrato lleva el
  nombre, la dirección y los honorarios del cliente, y no tiene por qué salir
  de la máquina. El razonamiento completo está en `docs/OPEN_MODEL.md`. No
  conviertas a Claude en requisito.
- Los dos backends de modelo se llaman con el mismo esquema JSON (`format` en
  Ollama, `output_config.format` en Claude). Si añades un agente, defínele su
  esquema: ningún agente parsea prosa.

---

# Reglas de UI: nada de "look de IA"

En cualquier interfaz que se diseñe o construya en este proyecto, **no** se
construyen desde cero componentes que ya existen en una librería probada. Stack
obligatorio:

## 1. Fundaciones (siempre)

- Base: **shadcn/ui**, sobre **Radix** o **Base UI** para primitivas accesibles
  (dialog, popover, select, tabs, tooltip, etc.).
- Nunca dejar shadcn con su estilo por defecto. Antes de construir pantallas,
  definir tokens propios (paleta, tipografía, radios, sombras, espaciado) en el
  tema y aplicarlos. Evitar las combinaciones genéricas: gris zinc + radio xl +
  sombra suave + degradado morado.

## 2. Especialistas (obligatorios para estos casos)

| Caso | Librería |
| --- | --- |
| Toasts / notificaciones | **Sonner** |
| Drawers / bottom sheets | **Vaul** |
| Command menu / búsqueda ⌘K | **cmdk** |
| Números que cambian (contadores, precios, KPIs) | **NumberFlow** |

No se reimplementan a mano: se suelen omitir los detalles de animación, gestos,
foco y accesibilidad.

## 3. Componentes de diseño (con moderación)

- Para un elemento destacado: **Magic UI**, **Aceternity UI**, **21st.dev**,
  **Beautiful UI** o **RareUI**.
- **Regla de un solo destacado:** como máximo UN componente llamativo por
  pantalla (un hero animado, un fondo especial, etc.). El resto, sobrio.

## Proceso

1. Antes de escribir código de UI, decir qué librería se usará para cada
   componente y por qué.
2. Si un componente no encaja en ninguna librería, avisar antes de construirlo a
   mano.
3. Si el proyecto ya tiene un sistema de diseño o librería de componentes,
   respetarlo y usar este stack solo para lo que falte.
4. Instalar las dependencias con el gestor de paquetes del proyecto y seguir la
   documentación oficial de cada librería (CLI de shadcn:
   `npx shadcn@latest add ...`).

---

## Cómo se aplica en este repositorio

El frontend vive en `web/` (Vite + React + TypeScript + Tailwind + shadcn/ui) y
**se compila a `app/static/`**, que es lo que sirve FastAPI. El `dist` compilado
se versiona a propósito: un juez del hackathon debe poder clonar y correr con
`pip install -r requirements.txt` + `uvicorn`, sin Node.

```bash
cd web && npm install && npm run build   # escribe en ../app/static
```

Asignación de librerías en el panel:

| Elemento | Librería |
| --- | --- |
| Dialog de revisión de factura, de cobro y de reparto | shadcn/ui `dialog` (Radix) |
| Tabs del panel, tooltips, badges, botones, cards, inputs | shadcn/ui |
| Avisos de "factura enviada", "pago recibido", errores de PayPal | Sonner |
| KPIs (facturado, cobrado, en riesgo) | NumberFlow |
| Paleta de comandos ⌘K con las acciones del agente | cmdk |
| Tablas de hitos, facturas, repartos y bitácora | AG Grid Community |
| Único destacado por pantalla | la barra de riesgo del hito en mora |

Tokens de tema en `web/src/index.css`: no usar la paleta por defecto de shadcn.
