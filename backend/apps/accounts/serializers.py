from rest_framework import serializers

from .models import User


class LoginSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class MeSerializer(serializers.ModelSerializer[User]):
    id = serializers.UUIDField(source="public_id", read_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "full_name")
        read_only_fields = fields
