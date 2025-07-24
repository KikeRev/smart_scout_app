# dashboard/chat/views.py
import json
import requests
from django.http import StreamingHttpResponse, JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt  # si usas CSRF token, no lo quites

from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.views.generic import ListView, TemplateView
from django.shortcuts import get_object_or_404, redirect
from apps.dashboard.chats.models import ChatSession, Message
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import DetailView

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.middleware.csrf import get_token
from django.utils import timezone

FASTAPI = "http://api:8001"   # ajusta si tienes otra URL

@method_decorator(login_required, name="dispatch")
class ChatListView(ListView):
    template_name = "chats/list.html"
    context_object_name = "sessions"

    def get_queryset(self):
        return ChatSession.objects.filter(user=self.request.user).order_by("-updated_at")[:50]

@login_required
def new_chat_redirect(request):
    sess = ChatSession.objects.create(user=request.user)
    return redirect("chats:session", pk=sess.id)

@method_decorator(login_required, name="dispatch")
class ChatSessionView(TemplateView):
    template_name = "chats/session.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        session = get_object_or_404(ChatSession, pk=kwargs["pk"], user=self.request.user)
        ctx["session"] = session
        ctx["messages"] = session.message_set.order_by("created_at")
        return ctx

@method_decorator(login_required, name="dispatch")
class ChatDetailView(LoginRequiredMixin, DetailView):
    model = ChatSession
    template_name = "chats/session.html"   # o el que prefieras
    context_object_name = "session"

    def get_queryset(self):
        # filtra por usuario → nadie ve las sesiones de otros
        return super().get_queryset().filter(user=self.request.user)

@login_required
@transaction.atomic
def chat_api(request):
    data = json.loads(request.body)
    text = data["message"].strip()
    user = request.user

    # 1. crea sesión si viene session_id o crea nueva
    session_id = data.get("session_id")
    if session_id:
        session = ChatSession.objects.select_for_update().get(id=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user)

    Message.objects.create(session=session, role="user", content=text)

    # 2. llama al agente con user.id para que guarde contexto allí
    payload = {"message": text, "user_id": str(user.id)}
    r = requests.post(f"{FASTAPI}/chat/", json=payload, timeout=120)
    r.raise_for_status()
    answer = r.json()["answer"]

    Message.objects.create(session=session, role="assistant", content=answer)

    # 3. Primera respuesta → define título
    if not session.title:
        session.title = answer.split("\n", 1)[0][:100]  # primer renglón / 100 chars
        session.save(update_fields=["title"])

    return JsonResponse({
        "session_id": session.id,
        "answer":     answer,
    })

@login_required
@csrf_exempt
@transaction.atomic
def chat_stream(request):
    """
    Devuelve la respuesta del agente como un stream (SSE o chunks JSON-lines).
    Front-end: abrir con fetch y procesar línea a línea.
    """
    data = json.loads(request.body)
    text = data["message"].strip()
    user = request.user

    # 1. crear/recuperar la sesión del usuario
    session_id = data.get("session_id")
    if session_id:
        session = ChatSession.objects.select_for_update().get(id=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user)

    Message.objects.create(session=session, role="user", content=text)

    def event_stream():
        """
        Generador que:
        1. abre conexión al agente en modo stream
        2. va reenviando los trozos al navegador y guardándolos en la BD
        3. cierra guardando el mensaje completo
        Formato de salida = Server-Sent Events:
          data: <chunk>\n\n
        """
        # -------------------------------------------
        # abrir el stream hacia FastAPI
        # -------------------------------------------
        payload = {"message": text, "user_id": str(user.id), "stream": True}
        with requests.post(
            f"{FASTAPI}/chat/",
            json=payload,
            timeout=300,
            stream=True,
        ) as r:
            r.raise_for_status()

            assistant_chunks = []   # para agrupar el mensaje final

            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue  # keep-alive vacías

                # FastAPI envía JSON-lines: {"content": "...", "finish": false}
                obj = json.loads(raw)
                delta = obj.get("content", "")
                assistant_chunks.append(delta)

                # ------  emitir al navegador (SSE) ------
                yield f"data: {delta}\n\n"

            full_answer = "".join(assistant_chunks)

        # guardar el mensaje completo cuando termina
        Message.objects.create(session=session, role="assistant", content=full_answer)

        # si era la 1ª respuesta -> título
        if not session.title:
            session.title = full_answer.split("\n", 1)[0][:100]
            session.save(update_fields=["title"])

        # evento especial para cerrar stream y pasar session_id
        yield f"event: done\ndata: {json.dumps({'session_id': session.id})}\n\n"

    # Cabeceras SSE
    headers = {
        "Content-Type":  "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # nginx
    }
    return StreamingHttpResponse(event_stream(), headers=headers)



@login_required
@transaction.atomic
def chat_message(request, pk):
    """
    Recibe un POST HTMX con el texto del usuario,
    llama al agente (sin stream) y devuelve el fragmento
    HTML de los dos mensajes (user + assistant).
    """
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    text     = request.POST.get("text", "").strip()
    if not text:
        return HttpResponse(status=204)

    # guarda mensaje del usuario
    m_user = Message.objects.create(
        session=session, role="user", content=text, created_at=timezone.now()
    )

    # llamada síncrona a FastAPI
    payload = {"message": text, "user_id": str(request.user.id)}
    r = requests.post(f"{FASTAPI}/chat/", json=payload, timeout=120)
    r.raise_for_status()
    answer = r.json()["answer"]

    # guarda respuesta del asistente
    m_bot = Message.objects.create(
        session=session, role="assistant", content=answer, created_at=timezone.now()
    )

    # actualiza título la 1ª vez
    if not session.title:
        session.title = answer.split("\n", 1)[0][:100]
        session.save(update_fields=["title"])

    # devuelve el HTML de ambos mensajes para que HTMX los inserte
    rendered = render_to_string(
        "chats/_message.html",
        {"m": m_user},
        request=request,
    ) + render_to_string(
        "chats/_message.html",
        {"m": m_bot},
        request=request,
    )

    return HttpResponse(rendered)

