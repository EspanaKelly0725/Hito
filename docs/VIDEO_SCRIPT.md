# Hito — demo video script (2:50)

Narration in English. Stage directions in Spanish, in parentheses, above each
line. Record the screen first, cut it down, then narrate against the cut.

**Antes de grabar**

- `setx OLLAMA_KEEP_ALIVE 30m`, reinicia Ollama y pasa un contrato de
  calentamiento. La primera llamada en frío cuesta 50 segundos extra.
- ⌘K → Reset everything. Navegador maximizado, modo claro, 1920×1080.
- Ten abierta en otra pestaña la bandeja del comprador sandbox de PayPal.
- Silencia las notificaciones de Windows.

**Al editar:** cada llamada al modelo tarda entre 25 y 60 segundos. Corta sobre
el aviso que dice qué está haciendo y retoma en el resultado. Son cuatro cortes.

---

## 1 · HOOK — 0:00 to 0:22

*(Pantalla fija en el panel de Hito con la factura vencida visible. No te muevas
todavía. Deja que el 45% y los $1.351 se lean.)*

> Laura is a designer in Medellín. A client in Texas owes her nine thousand
> dollars, in three payments.
>
> She delivered the first one a month ago. The invoice is fifteen days late.
> And she still has not sent the reminder — because asking for money she has
> already earned makes her uncomfortable.

*(Señala con el cursor la tarjeta "What needs you".)*

> That hesitation is not a personality flaw. For a freelancer, it is the most
> expensive habit there is.
>
> This is Hito. It reads her contract, it bills her client, and it does the
> part she dreads.

---

## 2 · DEVELOPMENT — 0:22 to 2:15

### Lee el contrato — 0:22

*(⌘K → Reset everything. Arrastra el PDF del contrato a la zona de carga.
Corta aquí la espera del modelo.)*

> It starts with the contract. A PDF, the way it actually arrives.

*(Aparece la pantalla de aprobación. Pausa 3 segundos sobre la tabla.)*

> Three deliverables. Three thousand dollars each. With the due dates, the
> collaborators, and their share of every payment.

*(Señala la columna "Where it says so".)*

> And behind every line, the sentence from the contract it came from. Laura has
> to approve this, and "trust me" is not an approval.

*(Señala la caja ámbar de advertencias.)*

> It also read what is missing. No late-payment clause. No acceptance criteria
> for the brand manual. Nobody writes that in a contract until it costs them.

*(Clic en "Approve this plan".)*

> Nothing exists until she approves it.

### Entrega y factura — 0:52

*(Clic en "I delivered this" del primer hito. Corta la espera del revisor.)*

> She delivers the logo. And here is where Hito stops being a wrapper around a
> model.

*(Se abre el diálogo del revisor. Pausa 4 segundos sobre la lista de
comprobaciones.)*

> Before anything is sent, a second reviewer checks the invoice against the
> contract. Seven deterministic checks in code — the amount, the recipient, the
> currency, whether this milestone was already billed, whether it would take the
> project past the contract total.

*(Señala la cita del contrato en el diálogo.)*

> And an independent model pass that answers a different question: does this
> invoice match what the client actually agreed to pay for? It quotes the
> clause — and the quote is verified against the contract text, so a convincing
> paraphrase never reaches her.
>
> The agent that writes the invoice is never the agent that approves it.

*(Cambia a la pestaña de PayPal sandbox y muestra la factura recibida. Pausa 4
segundos. Vuelve a Hito.)*

> Both agree, so it goes out. That is a real PayPal invoice, in the sandbox,
> created through the Invoicing API.

### Cobra con criterio — 1:25

*(Pestaña "Invoices & risk". Pausa sobre la fila vencida.)*

> Then the second invoice goes past due. This is the part Laura hates.

*(Clic en "Chase with tact". Corta la espera del modelo.)*

> Hito scores how likely it is that this one is never paid. Forty-five percent.

*(Se abre el diálogo. Señala el medidor y la escala de bandas.)*

> That number is not a guess. It is a logistic regression, trained on this
> client's own payment history — three invoices settled, one of them two weeks
> late. And the number picks the tone. Not Laura's mood on a Tuesday.
>
> Under twenty-four percent, a friendly nudge. Over fifty-two, Hito offers to
> split the balance in two. Forty-five lands in the middle, so the draft is
> firm: a date, an amount, and the contract clause.

*(Señala la caja ámbar "Check these before sending". Pausa 4 segundos.)*

> And look at this. The model wrote that this was her final reminder. It is the
> first. It opened with filler she would never write.
>
> So something checks the draft too, against what the model was actually given.
> It does not rewrite it behind her. It shows her, and she decides.

### Reparte — 1:55

*(Vuelve a "The flow". Clic en "Split it" del hito pagado. Corta la espera.)*

> The first payment arrived, so Hito splits it. Thirty percent to the developer,
> twenty to the illustrator.

*(Se abre el diálogo. Señala el ítem en ámbar sin marcar.)*

> The amounts are computed in code, never by the model. And the developer's nine
> hundred dollars is above Laura's ceiling, so Hito will not send it alone. She
> ticks that one line.

*(Marca la casilla y clic en "Approve and send". Pausa 3 segundos.)*

> Then it goes out through PayPal Payouts.

---

## 3 · CLOSE — 2:15 to 2:50

*(Pestaña "Audit trail". Desplázate despacio por la columna "Decided by".)*

> Every decision is in one ledger, and it says who made it. Agent. Laura. Agent.
> PayPal. Laura.
>
> That column is the whole design. The agent does the work. The human keeps the
> decisions that have consequences.

*(Señala la cabecera donde dice "AI: qwen2.5:3b · local".)*

> And all of this runs on an open-source model, on her own laptop. A contract
> carries a client's legal name, their address, and what they pay. It never
> leaves the machine.

*(Pantalla fija en el panel completo.)*

> Hito does not make Laura braver about asking for her money.
>
> It makes the asking a consequence of the risk — so the invoice that needs
> chasing gets chased, in the register it deserves, on the day it is due.
>
> That is the difference between getting paid and getting paid eventually.

---

## Checklist antes de subir

- [ ] Menos de 3:00
- [ ] La factura real de PayPal aparece en pantalla
- [ ] El diálogo del revisor aparece en pantalla
- [ ] El 44% y el tono que eligió aparecen juntos
- [ ] El techo de aprobación bloqueando un pago aparece en pantalla
- [ ] Sin música ni material de terceros con derechos
- [ ] Subido a YouTube como **público**
