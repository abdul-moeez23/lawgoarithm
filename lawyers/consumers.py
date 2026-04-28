import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

class LawyerDashboardConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        
        if not self.user.is_authenticated or self.user.role != 'lawyer':
            await self.close()
            return

        # Create a unique group for this lawyer
        self.group_name = f"lawyer_{self.user.id}"

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

        # Update status to online globally
        await self.update_user_status(True)
        # Broadcast online status to all active case chats
        await self.broadcast_status_to_chats('online')

    async def disconnect(self, close_code):
        # Update status to offline
        if self.user.is_authenticated:
            await self.update_user_status(False)
            # Broadcast offline status to active case chats
            await self.broadcast_status_to_chats('offline')

        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def broadcast_status_to_chats(self, status):
        """
        Finds all active cases for the lawyer and broadcasts their new status
        to the corresponding chat groups.
        """
        case_ids = await self.get_active_case_ids()
        
        for cid in case_ids:
            await self.channel_layer.group_send(
                f'chat_{cid}',
                {
                    'type': 'user_status_update',
                    'user_id': self.user.id,
                    'status': status
                }
            )

    @database_sync_to_async
    def update_user_status(self, is_online):
        """Update user's online status in the database"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(pk=self.user.pk).update(is_online=is_online)

    @database_sync_to_async
    def get_active_case_ids(self):
        """
        Get IDs of all cases where this lawyer is hired or accepted.
        """
        from clients.models import Interaction
        try:
            return list(Interaction.objects.filter(
                lawyer__user=self.user,
                status__in=['accepted', 'hired']
            ).values_list('case_id', flat=True))
        except Exception:
            return []

    async def new_connection_request(self, event):
        """
        Handler for 'new_connection_request' type messages sending to this group.
        """
        await self.send(text_data=json.dumps({
            'type': 'new_connection_request',
            'data': event['data']
        }))

    async def case_hired_notification(self, event):
        """
        Handler for when a lawyer is officially hired.
        """
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'status': 'hired',
            'message': event['message'],
            'case_id': event['case_id']
        }))

    async def chat_message(self, event):
        """
        Handler for incoming chat messages to update dashboard globally.
        """
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'case_id': event.get('case_id'),
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp']
        }))

    async def receive(self, text_data):
        """
        Receive message from WebSocket.
        Expected format: {"action": "delete_document", "document_id": 123, "mode": "me"|"everyone"}
        """
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'delete_document':
                document_id = data.get('document_id')
                mode = data.get('mode')
                if document_id and mode:
                    await self.handle_document_deletion(document_id, mode)
        except json.JSONDecodeError:
            pass

    async def handle_document_deletion(self, document_id, mode):
        """Perform deletion and broadcast to case group"""
        result = await self.delete_document_db(document_id, mode)
        
        if result['success']:
            if mode == 'everyone':
                # Broadcast to the specific case group so the client sees it removed
                if result['case_id']:
                    await self.channel_layer.group_send(
                        f'chat_{result["case_id"]}',
                        {
                            'type': 'document_deleted',
                            'document_id': document_id
                        }
                    )
                # Also notify the lawyer's dashboard connection to remove it from the list
                await self.send(text_data=json.dumps({
                    'type': 'document_deleted',
                    'document_id': document_id
                }))
            else:
                # Just notify the lawyer's dashboard to hide it locally
                await self.send(text_data=json.dumps({
                    'type': 'document_deleted',
                    'document_id': document_id,
                    'mode': 'me'
                }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result['message']
            }))

    @database_sync_to_async
    def delete_document_db(self, document_id, mode):
        """Synchronous DB operation for document deletion"""
        from clients.models import CaseDocument
        try:
            document = CaseDocument.objects.get(id=document_id)
            case_id = document.case.id
            
            # Permission check: Lawyer must be uploader or assigned to case
            if document.uploaded_by != self.user and not document.case.interactions.filter(lawyer__user=self.user, status__in=['accepted', 'hired']).exists():
                return {'success': False, 'message': 'Permission denied.'}

            if mode == 'me':
                document.hidden_for.add(self.user)
                return {'success': True, 'case_id': case_id}
            elif mode == 'everyone':
                if document.uploaded_by == self.user:
                    document.delete()
                    return {'success': True, 'case_id': case_id}
                else:
                    return {'success': False, 'message': 'Only the uploader can delete for everyone.'}
        except CaseDocument.DoesNotExist:
            return {'success': False, 'message': 'Document not found.'}
        except Exception as e:
            return {'success': False, 'message': str(e)}
