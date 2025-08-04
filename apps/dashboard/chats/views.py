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
from apps.agent_service.agents.factory import build_agent
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from apps.charts.models import TempChart
from pathlib import Path
from django.urls import reverse
import pandas as pd



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
class ChatSessionView(DetailView):
    """Pantalla de una conversación concreta"""
    model = ChatSession
    template_name = "chats/session.html"      # tu template
    context_object_name = "session"

    def get_queryset(self):
        # cada usuario sólo ve sus sesiones
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["messages"] = self.object.messages.order_by("created_at")
        return ctx

@method_decorator(login_required, name="dispatch")
class ChatDetailView(LoginRequiredMixin, DetailView):
    model = ChatSession
    template_name = "chats/session.html"   # o el que prefieras
    context_object_name = "session"

    def get_queryset(self):
        # filtra por usuario → nadie ve las sesiones de otros
        return super().get_queryset().filter(user=self.request.user)

# --------------------------------------------------------------------------- #
#  1)  /chat  – respuesta completa JSON
# --------------------------------------------------------------------------- #
@login_required
@transaction.atomic
def chat_api(request):
    data  = json.loads(request.body)
    text  = data["message"].strip()
    user  = request.user

    # 1. sesión (crea o recupera)
    session_id = data.get("session_id")
    if session_id:
        session = ChatSession.objects.select_for_update().get(id=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user)

    # 2. guarda el turno del usuario  (✔ una sola vez)
    Message.objects.create(session=session, role="user", content=text)

    # 3. prepara histórico (k = 20 últimos)
    past = session.messages.order_by("-created_at")[:20][::-1]
    history = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in past
    ]

    # 4. invoca al micro‑servicio FastAPI
    payload = {
        "session_id": str(session.id),
        "user_id":    str(user.id),
        "message":    text,
        "messages":   history,
    }
    r = requests.post(f"{FASTAPI}/chat/", json=payload, timeout=120)
    r.raise_for_status()
    answer = r.json()["answer"]

    # 5. guarda la respuesta del asistente
    Message.objects.create(session=session, role="assistant", content=answer)

    # 6. título automático (primera vez)
    if not session.title:
        session.title = answer.split("\n", 1)[0][:100]
        session.save(update_fields=["title"])

    return JsonResponse({"session_id": session.id, "answer": answer})


# --------------------------------------------------------------------------- #
#  2)  /chat – streaming (Server‑Sent Events)
# --------------------------------------------------------------------------- #
@login_required
@csrf_exempt
@transaction.atomic
def chat_stream(request):
    data  = json.loads(request.body)
    text  = data["message"].strip()
    user  = request.user

    # 1. sesión (crea o recupera)
    session_id = data.get("session_id")
    if session_id:
        session = ChatSession.objects.select_for_update().get(id=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user)

    # 2. guarda el turno del usuario (✔ una sola vez)
    Message.objects.create(session=session, role="user", content=text)

    # 3. histórico para el agente
    past = session.messages.order_by("-created_at")[:20][::-1]
    history = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in past
    ]

    # 4. generador SSE
    def event_stream():
        payload = {
            "session_id": str(session.id),
            "user_id":    str(user.id),
            "message":    text,
            "messages":   history,
            "stream":     True,
        }
        with requests.post(
            f"{FASTAPI}/chat/",
            json=payload,
            timeout=300,
            stream=True,
        ) as r:
            r.raise_for_status()
            assistant_chunks = []

            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                obj   = json.loads(raw)
                delta = obj.get("content", "")
                assistant_chunks.append(delta)
                yield f"data: {delta}\n\n"      # envía token al navegador

            full_answer = "".join(assistant_chunks)

        # 5. guarda la respuesta completa
        Message.objects.create(session=session, role="assistant", content=full_answer)

        # 6. título automático
        if not session.title:
            session.title = full_answer.split("\n", 1)[0][:100]
            session.save(update_fields=["title"])

        # 7. marca fin de stream
        yield f"event: done\ndata: {json.dumps({'session_id': session.id})}\n\n"

    headers = {
        "Content-Type":      "text/event-stream",
        "Cache-Control":     "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingHttpResponse(event_stream(), headers=headers)

@login_required
@transaction.atomic
def chat_message(request, pk):
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)

    text_in = request.POST.get("text", "").strip()
    if not text_in:
        return HttpResponse(status=204)

    # ------------------ 1) memoria ------------------
    past_msgs = session.messages.order_by("created_at")
    agent = build_agent(user_id=str(request.user.id), messages=past_msgs)

    # ------------------ 2) AGENTE -------------------
    raw = agent.invoke({"input": text_in})["output"]

    if isinstance(raw, dict):
        answer_text = raw.get("text", "")
        attachments = raw.get("attachments", [])        # lista [{}]
    else:                                               # fallback
        answer_text = str(raw)
        attachments = []

    # ------------------ 3) PERSISTENCIA -------------
    m_user, m_bot = Message.objects.bulk_create([
        Message(session=session, role="user",      content=text_in),
        Message(session=session, role="assistant", content=answer_text,
                meta=attachments),                 #  <<<<<<<<<<<<<<
    ])

    if not session.title:
        session.title = answer_text.split("\n", 1)[0][:100]
        session.save(update_fields=["title"])

    # ------------------ 4) RENDER -------------------
    rendered = (
        render_to_string("chats/_message.html", {"m": m_user}, request=request) +
        render_to_string("chats/_message.html", {"m": m_bot},  request=request)
    )
    return HttpResponse(rendered)

# --------------------------------------------------------------------------- #
#  Elimina una sesión de chat (y sus mensajes)
# --------------------------------------------------------------------------- #
from django.urls import reverse

@login_required
@require_POST          # ← en lugar de DELETE
@csrf_protect 
def chat_delete(request, pk):
    """
    Borra una ChatSession (y sus mensajes en cascada).
    Devuelve 204 para que HTMX quite el nodo del DOM.
    """
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.delete()
    return HttpResponse(status=204, headers={"HX-Redirect": reverse("chats:list")})



def serve_chart(request, pk):
    obj = get_object_or_404(TempChart, pk=pk)
    return redirect(obj.image.url)  

