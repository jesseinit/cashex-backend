# Generated by Django 3.1.5 on 2021-02-08 13:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userservice', '0006_auto_20210202_1441'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='address',
            field=models.CharField(default=None, max_length=300, null=True),
        ),
    ]