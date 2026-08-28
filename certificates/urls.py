from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("privacy/", views.privacy_policy, name="privacy_policy"),
    path("terms/", views.terms_of_service, name="terms_of_service"),
    path("create/", views.create_event, name="create_event"),
    path("event/<int:event_id>/position/", views.position_certificate, name="position_certificate"),
    path('event/<int:event_id>/delete/', views.delete_event, name='delete_event'),
    path("event/<int:event_id>/students/", views.student_list, name="student_list"),
    path("event/<int:event_id>/message/", views.update_message, name="update_message"),
    path("event/<int:event_id>/students/quick-add/", views.add_quick_send_student, name="add_quick_send_student"),
    path("event/<int:event_id>/students/<int:student_id>/edit/", views.update_student, name="update_student"),
    path("event/<int:event_id>/generate/", views.generate_all, name="generate_all"),
    path("event/<int:event_id>/send/", views.send_all, name="send_all"),
    path("event/<int:event_id>/send/<int:student_id>/", views.send_one, name="send_one"),
    path("verify/<uuid:cert_id>/", views.verify_certificate, name="verify_certificate"),
]
