from django.shortcuts import render
from rest_framework import generics, status

from consultant_menu.models import Consultant, Clients
from consultant_menu.serialazers import ConsultantSerializer
from rest_framework.views import APIView
from rest_framework.response import Response

class ConsultantAPIView(APIView):
    def get(self, request):
        consultants = Consultant.objects.all().values()
        return Response({'post':list(consultants)})

    def post(self, request):
        try:
            consultant = Consultant.objects.get(user=request.user)
        except Consultant.DoesNotExist:
            return Response(
                {'error': 'Consultant not found for this user'},
                status=status.HTTP_404_NOT_FOUND
            )
        post_new = Clients.objects.create(
            name=request.data.get('name'),
            number=request.data.get('number'),
            telegram_nickname=request.data.get('telegram_nickname'),
            who_your_consultant_name=consultant  # Автоматически прикрепляем к консультанту
        )

        return Response({
            'message': 'Client created successfully',
            'client_id': post_new.id,
            'consultant': consultant.first_name + ' ' + consultant.last_name
        }, status=status.HTTP_201_CREATED)



#class ConsultantAPIView(generics.ListAPIView):
#   queryset = Consultant.objects.all()
#    serializer_class = ConsultantSerializer
