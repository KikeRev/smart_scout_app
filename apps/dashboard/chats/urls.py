# apps/dashboard/chats/urls.py
from django.urls import path
from . import views

app_name = "chats"

urlpatterns = [
    # vistas HTML
    path("",          views.ChatListView.as_view(), name="list"),           # /chat/
    path("new/",      views.new_chat_redirect,       name="new"),           # /chat/new/
    #path("<uuid:pk>/", views.ChatSessionView.as_view(), name="session"),    # /chat/<id>/
    path("<int:pk>/",   views.ChatDetailView.as_view(),  name="session"),
    # endpoints AJAX / streaming
    path("api/",        views.chat_api,    name="chat_api"),                # POST /chat/api
    path("stream/",     views.chat_stream, name="chat_stream"),             # POST /chat/stream
]

