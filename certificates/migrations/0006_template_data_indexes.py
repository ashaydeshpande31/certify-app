from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('certificates', '0005_update_auto_continue'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='template_data',
            field=models.BinaryField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='template_type',
            field=models.CharField(blank=True, default='', max_length=60),
        ),
        migrations.AlterField(
            model_name='student',
            name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Pending'),
                    ('generated', 'Generated'),
                    ('sending', 'Sending'),
                    ('sent', 'Sent'),
                    ('failed', 'Failed'),
                ],
                default='pending',
                max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name='student',
            index=models.Index(fields=['event', 'status'], name='cert_stud_event_status_idx'),
        ),
        migrations.AddIndex(
            model_name='updaterecipient',
            index=models.Index(fields=['campaign', 'status'], name='cert_updrec_camp_status_idx'),
        ),
    ]
