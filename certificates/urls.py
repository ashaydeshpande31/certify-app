from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("create/", views.create_event, name="create_event"),
    path("event/<int:event_id>/position/", views.position_certificate, name="position_certificate"),
    path("event/<int:event_id>/students/", views.student_list, name="student_list"),
    path("event/<int:event_id>/generate/", views.generate_all, name="generate_all"),
    path("event/<int:event_id>/send/", views.send_all, name="send_all"),
    path("event/<int:event_id>/send/<int:student_id>/", views.send_one, name="send_one"),
    path("verify/<uuid:cert_id>/", views.verify_certificate, name="verify_certificate"),
]
