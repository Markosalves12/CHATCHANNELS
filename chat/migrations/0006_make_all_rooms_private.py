from django.db import migrations, models


def make_rooms_private(apps, schema_editor):
    ChatRoom = apps.get_model('chat', 'ChatRoom')
    RoomMembership = apps.get_model('chat', 'RoomMembership')

    for room in ChatRoom.objects.filter(is_private=False).iterator():
        RoomMembership.objects.get_or_create(
            room_id=room.id,
            user_id=room.created_by_id,
            defaults={'added_by_id': room.created_by_id},
        )

    ChatRoom.objects.filter(is_private=False).update(is_private=True)


class Migration(migrations.Migration):
    dependencies = [
        ('chat', '0005_chatroom_history_enabled'),
    ]

    operations = [
        migrations.RunPython(make_rooms_private, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='chatroom',
            name='is_private',
            field=models.BooleanField(default=True),
        ),
    ]
