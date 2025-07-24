# apps/dashboard/chats/urls.py
from django.urls import path
from . import views

app_name = "chats"

urlpatterns = [
    # vistas HTML
    path("",          views.ChatListView.as_view(), name="list"),           # /chat/
    path("new/",      views.new_chat_redirect,       name="new"),           # /chat/new/
    path("<int:pk>/message/", views.chat_message, name="message"),   # /chat/<id>/
    path("<int:pk>/",   views.ChatDetailView.as_view(),  name="session"),
    # endpoints AJAX / streaming
    path("api/",        views.chat_api,    name="chat_api"),                # POST /chat/api
    path("stream/",     views.chat_stream, name="chat_stream"),             # POST /chat/stream
]

