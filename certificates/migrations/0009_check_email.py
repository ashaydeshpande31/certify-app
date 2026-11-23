from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('certificates', '0008_extra_attachment'),
    ]

    operations = [
        migrations.CreateModel(
            name='SenderSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('check_email', models.EmailField(blank=True, max_length=254)),
                ('owner', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='sender_setting', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
