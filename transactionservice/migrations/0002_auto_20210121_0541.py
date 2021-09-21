# Generated by Django 3.1.5 on 2021-01-21 04:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('userservice', '0004_auto_20210115_1313'),
        ('transactionservice', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='exchangerequests',
            name='customer',
            field=models.ForeignKey(default=None, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='request_customer', to='userservice.user', verbose_name='The user who is requesting for exchange'),
        ),
        migrations.AlterField(
            model_name='exchangerequests',
            name='agent',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='request_agent', to='userservice.user', verbose_name='The user that would process this request'),
        ),
        migrations.AlterField(
            model_name='exchangetransactions',
            name='agent',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaction_agent', to='userservice.user', verbose_name='The user who is fufiling exchange request'),
        ),
        migrations.AlterField(
            model_name='exchangetransactions',
            name='customer',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='transaction_customer', to='userservice.user', verbose_name='The user who is requesting for exchange'),
        ),
    ]
