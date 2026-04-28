import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model
from django.utils import timezone
from .models import Case, Interaction, Message, MessageAuditLog, CaseDocument

User = get_user_model()


class InteractionStatusConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time interaction status updates.
    Clients connect to receive updates when lawyers accept/reject connection requests.
    """
    
    async def connect(self):
        self.user = self.scope["user"]
        self.case_id = None
        
        if not self.user.is_authenticated:
            await self.close()
            return

        # Join global client group for general notifications (like new case acceptance)
        self.client_group = f"client_{self.user.id}"
        await self.channel_layer.group_add(
            self.client_group,
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

        # Leave global client group
        if hasattr(self, 'client_group'):
            await self.channel_layer.group_discard(
                self.client_group,
                self.channel_name
            )

        # Leave case group if we were in one
        if self.case_id:
            await self.channel_layer.group_discard(
                f'case_{self.case_id}',
                self.channel_name
            )
    
    async def receive(self, text_data):
        """
        Receive message from WebSocket client.
        Expected format: {"action": "subscribe", "case_id": 123}
        """
        try:
            data = json.loads(text_data)
            action = data.get('action')
            
            if action == 'subscribe':
                case_id = data.get('case_id')
                if case_id:
                    await self.subscribe_to_case(case_id)
            elif action == 'unsubscribe':
                if self.case_id:
                    await self.unsubscribe_from_case()
        except json.JSONDecodeError:
            pass
    
    async def subscribe_to_case(self, case_id):
        """Subscribe to updates for a specific case"""
        # Verify user owns the case
        case = await self.get_case(case_id)
        if not case or case.client_id != self.user.id:
            await self.send(text_data=json.dumps({
                'error': 'Unauthorized access to case'
            }))
            return
        
        # Leave previous case group if any
        if self.case_id:
            await self.channel_layer.group_discard(
                f'case_{self.case_id}',
                self.channel_name
            )
        
        # Join new case group
        self.case_id = case_id
        await self.channel_layer.group_add(
            f'case_{self.case_id}',
            self.channel_name
        )
        
        # Send initial status
        await self.send_initial_status()
    
    async def unsubscribe_from_case(self):
        """Unsubscribe from case updates"""
        if self.case_id:
            await self.channel_layer.group_discard(
                f'case_{self.case_id}',
                self.channel_name
            )
            self.case_id = None
    
    async def send_initial_status(self):
        """Send current interaction statuses when client subscribes"""
        interactions = await self.get_case_interactions(self.case_id)
        status_map = {interaction['lawyer_id']: interaction['status'] for interaction in interactions}
        
        await self.send(text_data=json.dumps({
            'type': 'initial_status',
            'interactions': status_map
        }))
    async def interaction_status_update(self, event):
        """
        Handler for interaction status update messages sent to the group.
        This is called when a lawyer accepts/rejects a request.
        """
        await self.send(text_data=json.dumps({
            'type': 'status_update',
            'lawyer_id': event['lawyer_id'],
            'status': event['status'],
            'quoted_fee': event.get('quoted_fee'),
            'message': event.get('message', '')
        }))
    
    async def case_progress_update(self, event):
        """
        Handler for case progress updates.
        """
        await self.send(text_data=json.dumps({
            'type': 'case_progress_update',
            'detailed_status': event['detailed_status'],
            'progress_percentage': event['progress_percentage'],
            'next_hearing_date': event['next_hearing_date'],
            'status': event['status'],
            'updated_at': event['updated_at']
        }))

    async def notification_update(self, event):
        """
        Handler for general notifications.
        """
        await self.send(text_data=json.dumps({
            'type': 'notification_update',
            'message': event.get('message', 'New notification received'),
            'is_progress_update': event.get('is_progress_update', False),
            'case_id': event.get('case_id'),
            'detailed_status': event.get('detailed_status'),
            'progress_percentage': event.get('progress_percentage')
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

    async def broadcast_status_to_chats(self, status):
        """
        Finds all active cases for the user and broadcasts their new status
        to the corresponding chat groups (e.g. chat_123).
        """
        case_ids = await self.get_active_case_ids()
        
        for cid in case_ids:
            # We want to notify anyone in 'chat_{cid}' that THIS user status changed
            await self.channel_layer.group_send(
                f'chat_{cid}',
                {
                    'type': 'user_status_update',
                    'user_id': self.user.id,
                    'status': status
                }
            )

    @database_sync_to_async
    def get_case(self, case_id):
        """Get case by ID"""
        try:
            return Case.objects.get(pk=case_id)
        except Case.DoesNotExist:
            return None
    
    @database_sync_to_async
    def get_case_interactions(self, case_id):
        """Get all interactions for a case"""
        return list(
            Interaction.objects.filter(case_id=case_id)
            .values('lawyer_id', 'status')
        )
    
    @database_sync_to_async
    def update_user_status(self, is_online):
        """Update user's online status in the database"""
        User.objects.filter(pk=self.user.pk).update(is_online=is_online)

    @database_sync_to_async
    def get_active_case_ids(self):
        """
        Get IDs of all cases where this user is the client.
        We only care about cases where a chat might be active (accepted/hired/invited).
        """
        if self.user.role == 'client':
            return list(Case.objects.filter(client=self.user).values_list('id', flat=True))
        # If user is lawyer, this logic would differ, but InteractionStatusConsumer is primarily for clients
        # or general notifications.
        return []


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat between Lawyer and Client.
    """
    async def connect(self):
        self.case_id = self.scope['url_route']['kwargs']['case_id']
        self.room_group_name = f'chat_{self.case_id}'
        self.user = self.scope["user"]

        if not self.user.is_authenticated:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()
        
        # Update status to online
        await self.update_user_status(True)
        
        # Notify others in the room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_status_update',
                'user_id': self.user.id,
                'status': 'online'
            }
        )

    async def disconnect(self, close_code):
        # Update status to offline
        if self.user.is_authenticated:
            await self.update_user_status(False)
            
            # Notify others in the room
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'user_status_update',
                    'user_id': self.user.id,
                    'status': 'offline'
                }
            )

        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

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
            elif action == 'delete_message':
                message_id = data.get('message_id')
                mode = data.get('mode')
                if message_id and mode:
                    await self.handle_message_deletion(message_id, mode)
            elif action == 'clear_chat':
                await self.handle_clear_chat()
            elif action == 'delete_messages_bulk':
                message_ids = data.get('message_ids')
                if message_ids:
                    await self.handle_bulk_message_deletion(message_ids)
        except json.JSONDecodeError:
            pass

    async def handle_document_deletion(self, document_id, mode):
        """Perform deletion and broadcast if needed"""
        result = await self.delete_document_db(document_id, mode)
        
        if result['success']:
            if mode == 'everyone':
                # Broadcast to everyone in the case group
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'document_deleted',
                        'document_id': document_id
                    }
                )
            else:
                # Only notify the sender (the one who hidden it for themselves)
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

    async def handle_message_deletion(self, message_id, mode):
        """Perform message deletion and broadcast if needed"""
        result = await self.delete_message_db(message_id, mode)
        
        if result['success']:
            if mode == 'everyone':
                # Broadcast to everyone
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'message_deleted',
                        'message_id': message_id
                    }
                )
            else:
                # Only notify the requester
                await self.send(text_data=json.dumps({
                    'type': 'message_deleted',
                    'message_id': message_id,
                    'mode': 'me'
                }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result['message']
            }))

    async def handle_clear_chat(self):
        """Perform clear chat and notify sender"""
        result = await self.clear_chat_db()
        if result['success']:
            await self.send(text_data=json.dumps({
                'type': 'chat_cleared'
            }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result.get('message', 'Failed to clear chat.')
            }))

    async def handle_bulk_message_deletion(self, message_ids):
        """Perform bulk message deletion (for me) and notify sender"""
        result = await self.delete_messages_bulk_db(message_ids)
        if result['success']:
            await self.send(text_data=json.dumps({
                'type': 'messages_bulk_deleted',
                'message_ids': message_ids
            }))
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result.get('message', 'Failed to delete messages.')
            }))

    @database_sync_to_async
    def delete_document_db(self, document_id, mode):
        """Synchronous DB operation for document deletion"""
        try:
            document = CaseDocument.objects.get(id=document_id)
            
            # Permission check: User must be part of the case
            if document.case.client != self.user and not (self.user.role == 'lawyer' and document.case.interactions.filter(lawyer__user=self.user, status__in=['accepted', 'hired']).exists()):
                return {'success': False, 'message': 'Permission denied.'}

            if mode == 'me':
                document.hidden_for.add(self.user)
                return {'success': True}
            elif mode == 'everyone':
                if document.uploaded_by == self.user:
                    document.delete()
                    return {'success': True}
                else:
                    return {'success': False, 'message': 'Only the uploader can delete for everyone.'}
        except CaseDocument.DoesNotExist:
            return {'success': False, 'message': 'Document not found.'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @database_sync_to_async
    def delete_message_db(self, message_id, mode):
        """Synchronous DB operation for message deletion"""
        try:
            msg = Message.objects.get(id=message_id)
            
            # Permission check
            if msg.sender != self.user and msg.recipient != self.user:
                return {'success': False, 'message': 'Permission denied.'}

            if mode == 'me':
                msg.hidden_for.add(self.user)
                MessageAuditLog.objects.create(
                    message_id=msg.id,
                    case=msg.case,
                    user=self.user,
                    action='delete_me',
                    details=f"Message content: {msg.content[:50]}..."
                )
                return {'success': True}
            elif mode == 'everyone':
                if msg.sender != self.user:
                    return {'success': False, 'message': 'Only the sender can delete for everyone.'}
                
                # Check 2 minute condition
                time_diff = (timezone.now() - msg.created_at).total_seconds()
                if time_diff > 120:
                    return {'success': False, 'message': 'Cannot delete after 2 minutes.'}
                
                # Check not opened/read
                if msg.is_read:
                    return {'success': False, 'message': 'Message already read by recipient.'}
                
                # Check file not downloaded
                if msg.attachment and msg.is_attachment_downloaded:
                    return {'success': False, 'message': 'Attachment already downloaded.'}
                
                msg.save()
                
                MessageAuditLog.objects.create(
                    message_id=msg.id,
                    case=msg.case,
                    user=self.user,
                    action='delete_everyone',
                    details=f"Message content: {msg.content[:50]}..."
                )
                return {'success': True}
        except Message.DoesNotExist:
            return {'success': False, 'message': 'Message not found.'}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @database_sync_to_async
    def clear_chat_db(self):
        """Hides all messages in the case for the current user."""
        try:
            # We must make sure the user has access to this case
            # Just grabbing all messages associated with the case_id
            messages = Message.objects.filter(case_id=self.case_id)
            for msg in messages:
                # hide them
                msg.hidden_for.add(self.user)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    @database_sync_to_async
    def delete_messages_bulk_db(self, message_ids):
        """Synchronous DB operation for bulk message deletion (hide for me)"""
        try:
            messages = Message.objects.filter(id__in=message_ids)
            for msg in messages:
                # Permission check
                if msg.sender == self.user or msg.recipient == self.user:
                    msg.hidden_for.add(self.user)
            return {'success': True}
        except Exception as e:
            return {'success': False, 'message': str(e)}

    async def chat_message(self, event):
        """
        Receive message from room group and send to WebSocket.
        """
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'message_id': event.get('message_id'),
            'sender_id': event['sender_id'],
            'sender_name': event['sender_name'],
            'timestamp': event['timestamp']
        }))

    async def document_deleted(self, event):
        """
        Receive document deletion notification from group and send to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'document_deleted',
            'document_id': event['document_id']
        }))

    async def document_uploaded(self, event):
        """
        Receive document upload notification from group and send to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'document_uploaded',
            'doc': event['doc']
        }))

    async def message_deleted(self, event):
        """
        Receive message deletion notification from group and send to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id']
        }))

    async def user_status_update(self, event):
        """
        Receive user status update from room group and send to WebSocket.
        """
        await self.send(text_data=json.dumps({
            'type': 'user_status_update',
            'user_id': event['user_id'],
            'status': event['status']
        }))

    @database_sync_to_async
    def update_user_status(self, is_online):
        """Update user's online status in the database"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.filter(pk=self.user.pk).update(is_online=is_online)

