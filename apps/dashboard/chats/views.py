# dashboard/chat/views.py
import json
import requests
from django.http import StreamingHttpResponse, JsonResponse
from django.db import transaction
from django.views.decorators.csrf import csrf_exempt  # if you use CSRF token, don't remove it

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



FASTAPI = "http://api:8001"   # adjust if you have another URL

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
    """Screen of a specific conversation"""
    model = ChatSession
    template_name = "chats/session.html"      # your template
    context_object_name = "session"

    def get_queryset(self):
        # each user only sees their sessions
        return super().get_queryset().filter(user=self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["messages"] = self.object.messages.order_by("created_at")
        # Add user's chat list for the sidebar
        ctx["user_chats"] = ChatSession.objects.filter(user=self.request.user).order_by("-updated_at")[:20]
        return ctx

@method_decorator(login_required, name="dispatch")
class ChatDetailView(LoginRequiredMixin, DetailView):
    model = ChatSession
    template_name = "chats/session.html"   # or whichever you prefer
    context_object_name = "session"

    def get_queryset(self):
        # filter by user → no one sees other people's sessions
        return super().get_queryset().filter(user=self.request.user)

# --------------------------------------------------------------------------- #
#  1)  /chat  – complete JSON response
# --------------------------------------------------------------------------- #
@login_required
@transaction.atomic
def chat_api(request):
    data  = json.loads(request.body)
    text  = data["message"].strip()
    user  = request.user

    # 1. session (create or retrieve)
    session_id = data.get("session_id")
    if session_id:
        session = ChatSession.objects.select_for_update().get(id=session_id, user=user)
    else:
        session = ChatSession.objects.create(user=user)

    # 2. save user's turn (✔ only once)
    Message.objects.create(session=session, role="user", content=text)

    # 3. prepara histórico (k = 20 últimos)
    past = session.messages.order_by("-created_at")[:20][::-1]
    history = [
        {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        for m in past
    ]

    # 4. Invoque micro‑service FastAPI
    payload = {
        "session_id": str(session.id),
        "user_id":    str(user.id),
        "message":    text,
        "messages":   history,
    }
    r = requests.post(f"{FASTAPI}/chat/", json=payload, timeout=120)
    r.raise_for_status()
    answer = r.json()["answer"]

    # 5. Save the assistant's response
    Message.objects.create(session=session, role="assistant", content=answer)

    # 6. Automatic title (first time)
    if not session.title:
        session.title = answer.split("\n", 1)[0][:100]
        session.save(update_fields=["title"])

    return JsonResponse({"session_id": session.id, "answer": answer})


@login_required
def chat_stream(request, pk):
    """SSE streaming endpoint for real-time TAO events"""
    import threading
    import queue as queue_module
    
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    text_in = request.POST.get("text", "").strip()
    
    if not text_in:
        return HttpResponse(status=204)
    
    # Detect language
    spanish_keywords = ["busca", "genera", "crea", "dame", "encuentra", "muestra", "compara", "analiza"]
    language = "es" if any(word in text_in.lower() for word in spanish_keywords) else "en"
    
    # Queue for TAO events
    tao_queue = queue_module.Queue()
    
    # Agent execution in background thread
    def run_agent():
        from apps.agent_service.agents.tao_callback import TAOCallback
        
        # Create TAO callback with event queue
        tao_callback = TAOCallback(language=language)
        tao_callback.event_queue = tao_queue
        
        print(f"[DJANGO DEBUG] Created TAO callback: {tao_callback}")
        print(f"[DJANGO DEBUG] Event queue assigned: {tao_queue}")
        
        past_msgs = session.messages.order_by("created_at")
        agent = build_agent(
            user_id=str(request.user.id),
            messages=past_msgs,
            language=language,
            callbacks=[tao_callback]  # Pass TAO callback explicitly
        )
        
        print(f"[DJANGO DEBUG] Agent built, has callbacks: {hasattr(agent, 'callbacks')}")
        
        # Execute agent with callbacks in config
        raw = agent.invoke(
            {
                "input": text_in,
                "user_id": str(request.user.id),
            },
            config={"callbacks": [tao_callback]}  # Pass callbacks in invoke config
        )["output"]
        
        # Signal completion with result
        tao_queue.put({"type": "done", "result": raw})
    
    # Start agent thread
    thread = threading.Thread(target=run_agent)
    thread.start()
    
    def event_generator():
        from django.template.loader import render_to_string
        
        while True:
            event = tao_queue.get()
            
            if event["type"] == "tao":
                # Emit TAO event
                yield f"event: tao\ndata: {event['message']}\n\n"
            
            elif event["type"] == "done":
                # Process final result
                raw = event["result"]
                
                if isinstance(raw, dict):
                    answer_text = raw.get("text", "")
                    attachments = raw.get("attachments", [])
                else:
                    answer_text = str(raw)
                    attachments = []
                
                # Save messages
                with transaction.atomic():
                    m_user = Message.objects.create(session=session, role="user", content=text_in)
                    m_bot = Message.objects.create(
                        session=session,
                        role="assistant",
                        content=answer_text,
                        meta=attachments
                    )
                    
                    if not session.title:
                        session.title = answer_text.split("\n", 1)[0][:100]
                        session.save(update_fields=["title"])
                
                # Render HTML
                user_html = render_to_string("chats/_message.html", {"m": m_user}, request=request)
                bot_html = render_to_string("chats/_message.html", {"m": m_bot}, request=request)
                final_html = user_html + bot_html
                
                # Send done event
                import json
                yield f"event: done\ndata: {json.dumps({'html': final_html})}\n\n"
                break
    
    return StreamingHttpResponse(
        event_generator(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

@login_required
@transaction.atomic
def chat_message(request, pk):
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)

    text_in = request.POST.get("text", "").strip()
    if not text_in:
        return HttpResponse(status=204)

    # Detect user language (simple heuristic based on Spanish keywords)
    spanish_keywords = ["busca", "genera", "crea", "dame", "encuentra", "muestra", "compara", "analiza"]
    language = "es" if any(word in text_in.lower() for word in spanish_keywords) else "en"

    # ---------- 1) memory ----------
    past_msgs = session.messages.order_by("created_at")
    agent = build_agent(
        user_id=str(request.user.id), 
        messages=past_msgs,
        language=language
    )

    # ---------- 2) AGENT ----------
    raw = agent.invoke({
        "input": text_in,
        "user_id": str(request.user.id),  # pass user_id so tools can use Redis context
    })["output"]
    
    # ─── Get TAO events for transparency ───
    tao_events_markdown = ""
    if hasattr(agent, '_tao_callback'):
        tao_events_markdown = agent._tao_callback.get_events_markdown()

    # ­—— detect posible redirect (dashboard_inline) -------------
    redirect_url = raw.get("url") if isinstance(raw, dict) else None

    if isinstance(raw, dict):
        answer_text = raw.get("text", "")
        attachments = raw.get("attachments", [])
    else:                                    # fallback
        answer_text = str(raw)
        attachments = []
    
    # ─── Prepend TAO events to answer for transparency ───
    if tao_events_markdown:
        answer_text = tao_events_markdown + "\n\n" + answer_text

    # ---------- 3) PERSISTENCE ----------
    m_user, m_bot = Message.objects.bulk_create([
        Message(session=session, role="user",      content=text_in),
        Message(session=session, role="assistant", content=answer_text,
                meta=attachments),
    ])

    if not session.title:
        session.title = answer_text.split("\n", 1)[0][:100]
        session.save(update_fields=["title"])

    # ---------- 4) RENDER / DASHBOARD LINK ----------
    if isinstance(raw, dict) and raw.get("url"):
        link_html = render_to_string(
            "chats/_dashboard_link.html",
            {"url": raw["url"]},
            request=request,
        )
        # save the bot's message (empty text ≈ “ok, done”)
        Message.objects.create(
            session=session, role="assistant", content="",
            meta={"type": "dashboard", "url": raw["url"]},
        )
        return HttpResponse(
            render_to_string("chats/_message.html", {"m": m_user}, request=request)
            + link_html
        )

    rendered = (
        render_to_string("chats/_message.html", {"m": m_user}, request=request) +
        render_to_string("chats/_message.html", {"m": m_bot},  request=request)
    )
    return HttpResponse(rendered)

# --------------------------------------------------------------------------- #
#  (Delete a chat session (and its messages)
# --------------------------------------------------------------------------- #
@login_required
@require_POST          # ← instead of DELETE
@csrf_protect 
def chat_delete(request, pk):
    """
    Delete a ChatSession (and its messages).
    Return 204 to let HTMX remove the DOM node.
    """
    session = get_object_or_404(ChatSession, pk=pk, user=request.user)
    session.delete()
    return HttpResponse(status=204, headers={"HX-Redirect": reverse("chats:list")})

def serve_chart(request, pk):
    obj = get_object_or_404(TempChart, pk=pk)
    return redirect(obj.image.url)  

