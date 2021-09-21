# Generated by Django 3.1.5 on 2021-02-04 10:41

from django.conf import settings
import django.core.serializers.json
from django.db import migrations, models
import django.db.models.deletion
import utils.model_helpers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('transactionservice', '0005_exchangetransactions_cancellation_reason'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='TransactionPayments',
            fields=[
                ('id', models.CharField(default=utils.model_helpers.generate_id, editable=False, max_length=60, primary_key=True, serialize=False)),
                ('state', models.CharField(choices=[('active', 'active'), ('archived', 'archived'), ('deleted', 'deleted')], default='active', max_length=50)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('transaction_reference', models.CharField(max_length=100)),
                ('transaction_amount', models.BigIntegerField()),
                ('payment_status', models.CharField(choices=[('IN_ESCROW', 'IN_ESCROW'), ('REVERSED', 'REVERSED'), ('COMPLETED', 'COMPLETED')], default='IN_ESCROW', max_length=50)),
                ('payment_gateway', models.CharField(max_length=50)),
                ('payment_meta', models.JSONField(default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ('gateway_response', models.JSONField(default=dict, encoder=django.core.serializers.json.DjangoJSONEncoder)),
                ('inflow_escrow_at', models.DateTimeField(default=None, null=True)),
                ('reversed_at', models.DateTimeField(default=None, null=True)),
                ('completed_at', models.DateTimeField(default=None, null=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='transactionservice.exchangetransactions')),
            ],
            options={
                'db_table': 'TransactionPayments',
            },
        ),
        migrations.AddIndex(
            model_name='transactionpayments',
            index=models.Index(fields=['state', 'payment_status', 'transaction_reference'], name='Transaction_state_abe220_idx'),
        ),
    ]
