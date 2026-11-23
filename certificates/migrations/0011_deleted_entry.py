from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0010_settings'),
    ]

    operations = [
        migrations.CreateModel(
            name='DeletedEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('email', models.EmailField(max_length=254)),
                ('status', models.CharField(default='pending', max_length=10)),
                ('error_message', models.CharField(blank=True, max_length=300)),
                ('send_extra', models.BooleanField(default=False)),
                ('deleted_at', models.DateTimeField(auto_now_add=True)),
                ('campaign', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='deleted_entries', to='certificates.updatecampaign')),
                ('event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='deleted_entries', to='certificates.event')),
            ],
            options={'ordering': ['-deleted_at']},
        ),
    ]
