/**
 * TaskDetailScreen — create/edit a task with comments, assignee toggle,
 * due date picker, and status selector.
 *
 * Modes:
 * - Create: taskId === null → POST /collabs/{collabId}/tasks
 * - Edit:   taskId !== null → PATCH /tasks/{taskId}
 *
 * Comments:
 * - InfiniteScroll list (cursor pagination, 20/page)
 * - Keyboard-aware input (500ch limit with counter)
 *
 * Status FSM visual: todo → in_progress → done / blocked
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked';

interface Task {
  id: string;
  collab_id: string;
  title: string;
  description: string | null;
  assignee_profile_id: string | null;
  due_date: string | null;
  status: TaskStatus;
  order_key: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comment_count: number;
}

interface TaskComment {
  id: string;
  task_id: string;
  author_profile_id: string;
  body: string;
  created_at: string;
}

interface RouteParams {
  taskId: string | null;
  collabId: string;
  currentUserId: string;
  partnerUserId?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_OPTIONS: { value: TaskStatus; label: string; color: string }[] = [
  { value: 'todo', label: 'To Do', color: '#8E8E93' },
  { value: 'in_progress', label: 'In Progress', color: '#007AFF' },
  { value: 'done', label: 'Done', color: '#34C759' },
  { value: 'blocked', label: 'Blocked', color: '#FF3B30' },
];

const COMMENT_MAX_LENGTH = 500;

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const authToken = ''; // from auth context in production

async function fetchTask(taskId: string): Promise<Task> {
  const resp = await fetch(`/tasks/${taskId}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!resp.ok) throw new Error(`fetchTask: ${resp.status}`);
  return resp.json();
}

async function createTask(collabId: string, body: Partial<Task> & { order_key: string }): Promise<Task> {
  const resp = await fetch(`/collabs/${collabId}/tasks`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`createTask: ${resp.status}`);
  return resp.json();
}

async function patchTask(taskId: string, patch: Partial<Task>): Promise<Task> {
  const resp = await fetch(`/tasks/${taskId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`patchTask: ${resp.status}`);
  return resp.json();
}

async function deleteTask(taskId: string): Promise<void> {
  const resp = await fetch(`/tasks/${taskId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!resp.ok) throw new Error(`deleteTask: ${resp.status}`);
}

async function fetchComments(
  taskId: string,
  cursor?: string,
): Promise<{ comments: TaskComment[]; next_cursor: string | null }> {
  const params = cursor ? `?cursor=${cursor}&limit=20` : '?limit=20';
  const resp = await fetch(`/tasks/${taskId}/comments${params}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!resp.ok) throw new Error(`fetchComments: ${resp.status}`);
  return resp.json();
}

async function postComment(taskId: string, body: string): Promise<TaskComment> {
  const resp = await fetch(`/tasks/${taskId}/comments`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  });
  if (!resp.ok) throw new Error(`postComment: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// TaskDetailScreen
// ---------------------------------------------------------------------------

export default function TaskDetailScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute();
  const { taskId, collabId, currentUserId, partnerUserId } = route.params as RouteParams;

  const isCreateMode = taskId === null;

  // Form state
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [status, setStatus] = useState<TaskStatus>('todo');
  const [assigneeId, setAssigneeId] = useState<string | null>(null);
  const [dueDate, setDueDate] = useState<string | null>(null);

  // Comment state
  const [comments, setComments] = useState<TaskComment[]>([]);
  const [commentBody, setCommentBody] = useState('');
  const [commentCursor, setCommentCursor] = useState<string | null>(null);
  const [loadingComments, setLoadingComments] = useState(false);
  const [submittingComment, setSubmittingComment] = useState(false);

  // General loading
  const [loading, setLoading] = useState(!isCreateMode);
  const [saving, setSaving] = useState(false);

  // -----------------------------------------------------------------------
  // Load existing task
  // -----------------------------------------------------------------------

  useEffect(() => {
    if (isCreateMode) return;
    setLoading(true);
    fetchTask(taskId!)
      .then((t) => {
        setTitle(t.title);
        setDescription(t.description ?? '');
        setStatus(t.status);
        setAssigneeId(t.assignee_profile_id);
        setDueDate(t.due_date);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [taskId, isCreateMode]);

  // Load first page of comments
  useEffect(() => {
    if (isCreateMode || !taskId) return;
    loadComments();
  }, [taskId]);

  const loadComments = useCallback(
    async (cursor?: string) => {
      if (!taskId || loadingComments) return;
      setLoadingComments(true);
      try {
        const data = await fetchComments(taskId, cursor);
        setComments((prev) => (cursor ? [...prev, ...data.comments] : data.comments));
        setCommentCursor(data.next_cursor);
      } catch (err) {
        console.error('[TaskDetail] loadComments error:', err);
      } finally {
        setLoadingComments(false);
      }
    },
    [taskId, loadingComments],
  );

  // -----------------------------------------------------------------------
  // Save task
  // -----------------------------------------------------------------------

  const handleSave = useCallback(async () => {
    if (!title.trim()) {
      Alert.alert('Validation', 'Title is required.');
      return;
    }
    setSaving(true);
    try {
      if (isCreateMode) {
        await createTask(collabId, {
          title: title.trim(),
          description: description.trim() || null,
          assignee_profile_id: assigneeId ?? undefined,
          due_date: dueDate ?? undefined,
          order_key: 'i',  // Client should compute proper LexoRank key
          status: 'todo',
        } as any);
      } else {
        await patchTask(taskId!, {
          title: title.trim(),
          description: description.trim() || null,
          status,
          assignee_profile_id: assigneeId ?? undefined,
          due_date: dueDate ?? undefined,
        } as any);
      }
      navigation.goBack();
    } catch (err) {
      Alert.alert('Error', 'Failed to save task. Please try again.');
      console.error(err);
    } finally {
      setSaving(false);
    }
  }, [isCreateMode, taskId, collabId, title, description, status, assigneeId, dueDate, navigation]);

  // -----------------------------------------------------------------------
  // Delete task
  // -----------------------------------------------------------------------

  const handleDelete = useCallback(() => {
    if (!taskId) return;
    Alert.alert('Delete Task', 'Are you sure?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteTask(taskId);
            navigation.goBack();
          } catch {
            Alert.alert('Error', 'Failed to delete task.');
          }
        },
      },
    ]);
  }, [taskId, navigation]);

  // -----------------------------------------------------------------------
  // Submit comment
  // -----------------------------------------------------------------------

  const handleSubmitComment = useCallback(async () => {
    if (!taskId || !commentBody.trim() || submittingComment) return;
    setSubmittingComment(true);
    try {
      const newComment = await postComment(taskId, commentBody.trim());
      setComments((prev) => [...prev, newComment]);
      setCommentBody('');
    } catch {
      Alert.alert('Error', 'Failed to post comment.');
    } finally {
      setSubmittingComment(false);
    }
  }, [taskId, commentBody, submittingComment]);

  // -----------------------------------------------------------------------
  // Render
  // -----------------------------------------------------------------------

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" />
      </View>
    );
  }

  const participants = [currentUserId, partnerUserId].filter(Boolean) as string[];

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={88}
    >
      <ScrollView style={styles.scroll} contentContainerStyle={styles.scrollContent}>
        {/* Title */}
        <Text style={styles.label}>Title *</Text>
        <TextInput
          style={styles.input}
          value={title}
          onChangeText={setTitle}
          placeholder="Task title (max 200 chars)"
          maxLength={200}
          autoFocus={isCreateMode}
        />

        {/* Description */}
        <Text style={styles.label}>Description</Text>
        <TextInput
          style={[styles.input, styles.multilineInput]}
          value={description}
          onChangeText={setDescription}
          placeholder="Optional description…"
          maxLength={2000}
          multiline
          numberOfLines={4}
        />

        {/* Status picker */}
        {!isCreateMode && (
          <>
            <Text style={styles.label}>Status</Text>
            <View style={styles.statusRow}>
              {STATUS_OPTIONS.map((opt) => (
                <TouchableOpacity
                  key={opt.value}
                  style={[
                    styles.statusChip,
                    { borderColor: opt.color },
                    status === opt.value && { backgroundColor: opt.color },
                  ]}
                  onPress={() => setStatus(opt.value)}
                >
                  <Text
                    style={[
                      styles.statusChipText,
                      { color: opt.color },
                      status === opt.value && styles.statusChipTextActive,
                    ]}
                  >
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}

        {/* Assignee toggle */}
        <Text style={styles.label}>Assignee</Text>
        <View style={styles.assigneeRow}>
          <TouchableOpacity
            style={[styles.assigneeChip, assigneeId === null && styles.assigneeChipActive]}
            onPress={() => setAssigneeId(null)}
          >
            <Text style={styles.assigneeText}>Unassigned</Text>
          </TouchableOpacity>
          {participants.map((pid) => (
            <TouchableOpacity
              key={pid}
              style={[styles.assigneeChip, assigneeId === pid && styles.assigneeChipActive]}
              onPress={() => setAssigneeId(pid)}
            >
              <Text style={styles.assigneeText}>
                {pid === currentUserId ? 'Me' : 'Partner'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Due date (text input; production: DateTimePicker) */}
        <Text style={styles.label}>Due Date</Text>
        <TextInput
          style={styles.input}
          value={dueDate ?? ''}
          onChangeText={(v) => setDueDate(v || null)}
          placeholder="YYYY-MM-DD (optional)"
          maxLength={10}
          keyboardType="numeric"
        />

        {/* Save / Delete */}
        <View style={styles.actionRow}>
          <TouchableOpacity
            style={[styles.saveButton, saving && styles.buttonDisabled]}
            onPress={handleSave}
            disabled={saving}
          >
            <Text style={styles.saveText}>{saving ? 'Saving…' : isCreateMode ? 'Create Task' : 'Save Changes'}</Text>
          </TouchableOpacity>
          {!isCreateMode && (
            <TouchableOpacity style={styles.deleteButton} onPress={handleDelete}>
              <Text style={styles.deleteText}>Delete</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Comments section */}
        {!isCreateMode && (
          <>
            <Text style={[styles.label, styles.commentsHeader]}>Comments</Text>
            {comments.map((c) => (
              <View key={c.id} style={styles.commentBubble}>
                <Text style={styles.commentAuthor}>
                  {c.author_profile_id === currentUserId ? 'You' : 'Partner'}
                </Text>
                <Text style={styles.commentBody}>{c.body}</Text>
                <Text style={styles.commentTime}>
                  {new Date(c.created_at).toLocaleString()}
                </Text>
              </View>
            ))}
            {commentCursor && (
              <TouchableOpacity
                onPress={() => loadComments(commentCursor)}
                disabled={loadingComments}
                style={styles.loadMoreButton}
              >
                <Text style={styles.loadMoreText}>
                  {loadingComments ? 'Loading…' : 'Load more comments'}
                </Text>
              </TouchableOpacity>
            )}
          </>
        )}
      </ScrollView>

      {/* Comment input */}
      {!isCreateMode && (
        <View style={styles.commentInputRow}>
          <TextInput
            style={styles.commentInput}
            value={commentBody}
            onChangeText={(v) => setCommentBody(v.slice(0, COMMENT_MAX_LENGTH))}
            placeholder="Add a comment…"
            multiline
            maxLength={COMMENT_MAX_LENGTH}
          />
          <Text style={styles.charCounter}>
            {commentBody.length}/{COMMENT_MAX_LENGTH}
          </Text>
          <TouchableOpacity
            onPress={handleSubmitComment}
            disabled={!commentBody.trim() || submittingComment}
            style={[
              styles.sendButton,
              (!commentBody.trim() || submittingComment) && styles.buttonDisabled,
            ]}
          >
            <Text style={styles.sendText}>Send</Text>
          </TouchableOpacity>
        </View>
      )}
    </KeyboardAvoidingView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scroll: { flex: 1 },
  scrollContent: { padding: 16, paddingBottom: 32 },

  label: { fontSize: 13, fontWeight: '600', color: '#8E8E93', marginTop: 16, marginBottom: 6 },
  input: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 12,
    fontSize: 15,
    color: '#1C1C1E',
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#C6C6C8',
  },
  multilineInput: { height: 100, textAlignVertical: 'top' },

  statusRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  statusChip: {
    borderWidth: 1.5,
    borderRadius: 16,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
  statusChipText: { fontSize: 13, fontWeight: '500' },
  statusChipTextActive: { color: '#fff' },

  assigneeRow: { flexDirection: 'row', gap: 8 },
  assigneeChip: {
    borderWidth: 1,
    borderColor: '#C6C6C8',
    borderRadius: 16,
    paddingHorizontal: 14,
    paddingVertical: 6,
    backgroundColor: '#fff',
  },
  assigneeChipActive: { backgroundColor: '#007AFF', borderColor: '#007AFF' },
  assigneeText: { fontSize: 14, color: '#1C1C1E' },

  actionRow: { flexDirection: 'row', gap: 12, marginTop: 24 },
  saveButton: {
    flex: 1,
    backgroundColor: '#007AFF',
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: 'center',
  },
  saveText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  deleteButton: {
    paddingHorizontal: 20,
    paddingVertical: 14,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: '#FF3B30',
    alignItems: 'center',
  },
  deleteText: { color: '#FF3B30', fontSize: 16, fontWeight: '600' },
  buttonDisabled: { opacity: 0.4 },

  commentsHeader: { marginTop: 32, fontSize: 15 },
  commentBubble: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 12,
    marginTop: 8,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#C6C6C8',
  },
  commentAuthor: { fontSize: 12, fontWeight: '700', color: '#007AFF', marginBottom: 4 },
  commentBody: { fontSize: 14, color: '#1C1C1E' },
  commentTime: { fontSize: 11, color: '#8E8E93', marginTop: 4, textAlign: 'right' },

  loadMoreButton: { padding: 12, alignItems: 'center' },
  loadMoreText: { color: '#007AFF', fontSize: 14 },

  commentInputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 10,
    backgroundColor: '#fff',
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#C6C6C8',
  },
  commentInput: {
    flex: 1,
    backgroundColor: '#F2F2F7',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 8,
    fontSize: 14,
    maxHeight: 120,
  },
  charCounter: {
    fontSize: 11,
    color: '#8E8E93',
    marginHorizontal: 6,
    alignSelf: 'flex-end',
    marginBottom: 8,
  },
  sendButton: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    backgroundColor: '#007AFF',
    borderRadius: 18,
    alignSelf: 'flex-end',
  },
  sendText: { color: '#fff', fontSize: 14, fontWeight: '600' },
});
