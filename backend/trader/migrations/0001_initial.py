from django.db import migrations, models
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.CreateModel(
            name='Symbol',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=20)),
                ('description', models.CharField(max_length=200)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name='PO3Formation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timeframe', models.CharField(max_length=10)),
                ('phase', models.CharField(choices=[('accumulation', 'Accumulation'), ('manipulation', 'Manipulation'), ('distribution', 'Distribution')], max_length=20)),
                ('start_time', models.DateTimeField()),
                ('end_time', models.DateTimeField()),
                ('start_price', models.DecimalField(decimal_places=5, max_digits=10)),
                ('end_price', models.DecimalField(decimal_places=5, max_digits=10)),
                ('confidence', models.FloatField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('symbol', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trader.symbol')),
            ],
        ),
        migrations.CreateModel(
            name='Trade',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trade_type', models.CharField(choices=[('long', 'Long'), ('short', 'Short')], max_length=10)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('open', 'Open'), ('closed', 'Closed'), ('cancelled', 'Cancelled')], max_length=10)),
                ('entry_price', models.DecimalField(decimal_places=5, max_digits=10)),
                ('stop_loss', models.DecimalField(decimal_places=5, max_digits=10)),
                ('take_profit', models.DecimalField(decimal_places=5, max_digits=10)),
                ('position_size', models.DecimalField(decimal_places=5, max_digits=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('closed_at', models.DateTimeField(null=True)),
                ('pnl', models.DecimalField(decimal_places=2, max_digits=10, null=True)),
                ('po3_formation', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='trader.po3formation')),
                ('symbol', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='trader.symbol')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='auth.user')),
            ],
        ),
    ]
