/**
 * KanbanView — a horizontal 3-column board (todo | in_progress | done).
 *
 * Renders as a horizontally-scrollable view with vertical FlatLists per column.
 * Tap a card to open TaskDetailScreen.
 * Long-press a card to activate drag-and-drop across columns
 * (status change via PATCH on drop).
 *
 * Note: True cross-column drag-and-drop on RN requires a library like
 * `react-native-drag-and-drop-layout` or a custom PanResponder approach.
 * This implementation uses a tap-to-move affordance as a reliable fallback.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation } from '@react-navigation/native';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TaskStatus = 'todo' | 'in_progress' | 'done' | 'blocked';

interface Task {
  id: string;
  collab_id: string;
  title: string;
  status: TaskStatus;
  order_key: string;
  assignee_profile_id: string | null;
  due_date: string | null;
  comment_count: number;
  closed_at: string | null;
}

interface KanbanViewProps {
  collabId: string;
  currentUserId: string;
  authToken?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COLUMNS: { status: TaskStatus; label: string; color: string }[] = [
  { status: 'todo', label: 'To Do', color: '#8E8E93' },
  { status: 'in_progress', label: 'In Progress', color: '#007AFF' },
  { status: 'done', label: 'Done', color: '#34C759' },
];

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function fetchTasksByStatus(
  collabId: string,
  status: TaskStatus,
  authToken: string,
): Promise<Task[]> {
  const resp = await fetch(`/collabs/${collabId}/tasks?sort=order&status=${status}`, {
    headers: { Authorization: `Bearer ${authToken}` },
  });
  if (!resp.ok) throw new Error(`fetchTasks(${status}): ${resp.status}`);
  const data = await resp.json();
  return data.tasks;
}

async function moveTaskToStatus(
  taskId: string,
  newStatus: TaskStatus,
  authToken: string,
): Promise<void> {
  const resp = await fetch(`/tasks/${taskId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: newStatus }),
  });
  if (!resp.ok) throw new Error(`moveTask: ${resp.status}`);
}

// ---------------------------------------------------------------------------
// KanbanView
// ---------------------------------------------------------------------------

export default function KanbanView({
  collabId,
  currentUserId,
  authToken = '',
}: KanbanViewProps) {
  const navigation = useNavigation<any>();

  const [columns, setColumns] = useState<Record<TaskStatus, Task[]>>({
    todo: [],
    in_progress: [],
    done: [],
    blocked: [],
  });
  const [loading, setLoading] = useState(true);

  // -----------------------------------------------------------------------
  // Load all columns in parallel
  // -----------------------------------------------------------------------

  const loadAllColumns = useCallback(async () => {
    setLoading(true);
    try {
      const [todo, in_progress, done] = await Promise.all([
        fetchTasksByStatus(collabId, 'todo', authToken),
        fetchTasksByStatus(collabId, 'in_progress', authToken),
        fetchTasksByStatus(collabId, 'done', authToken),
      ]);
      setColumns((prev) => ({ ...prev, todo, in_progress, done }));
    } catch (err) {
      console.error('[KanbanView] Load error:', err);
    } finally {
      setLoading(false);
    }
  }, [collabId, authToken]);

  useEffect(() => {
    loadAllColumns();
  }, []);

  // -----------------------------------------------------------------------
  // Move task (tap-to-move affordance)
  // -----------------------------------------------------------------------

  const handleMoveTask = useCallback(
    async (task: Task, targetStatus: TaskStatus) => {
      if (task.status === targetStatus) return;

      // Optimistic update
      setColumns((prev) => {
        const next = { ...prev };
        next[task.status] = next[task.status].filter((t) => t.id !== task.id);
        next[targetStatus] = [{ ...task, status: targetStatus }, ...next[targetStatus]];
        return next;
      });

      try {
        await moveTaskToStatus(task.id, targetStatus, authToken);
      } catch {
        // Revert
        setColumns((prev) => {
          const next = { ...prev };
          next[targetStatus] = next[targetStatus].filter((t) => t.id !== task.id);
          next[task.status] = [task, ...next[task.status]];
          return next;
        });
      }
    },
    [authToken],
  );

  // -----------------------------------------------------------------------
  // Render card
  // -----------------------------------------------------------------------

  const renderCard = useCallback(
    (task: Task, columnStatus: TaskStatus) => {
      const isOverdue =
        task.due_date && task.status !== 'done' && new Date(task.due_date) < new Date();

      return (
        <Pressable
          key={task.id}
          style={[styles.card, isOverdue && styles.cardOverdue]}
          onPress={() =>
            navigation.navigate('TaskDetail', {
              taskId: task.id,
              collabId,
              currentUserId,
            })
          }
        >
          <Text style={styles.cardTitle} numberOfLines={3}>
            {task.title}
          </Text>
          {task.due_date && (
            <Text style={[styles.cardDue, isOverdue && styles.cardDueOverdue]}>
              Due {task.due_date}
            </Text>
          )}
          {task.assignee_profile_id === currentUserId && (
            <Text style={styles.cardAssignee}>Assigned to me</Text>
          )}
          {task.comment_count > 0 && (
            <Text style={styles.cardCommentCount}>💬 {task.comment_count}</Text>
          )}

          {/* Move buttons */}
          <View style={styles.moveRow}>
            {COLUMNS.filter((c) => c.status !== columnStatus).map((target) => (
              <TouchableOpacity
                key={target.status}
                style={[styles.moveChip, { borderColor: target.color }]}
                onPress={() => handleMoveTask(task, target.status)}
              >
                <Text style={[styles.moveChipText, { color: target.color }]}>
                  → {target.label}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </Pressable>
      );
    },
    [navigation, collabId, currentUserId, handleMoveTask],
  );

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

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.board}>
      {COLUMNS.map((col) => (
        <View key={col.status} style={styles.column}>
          {/* Column header */}
          <View style={[styles.columnHeader, { borderTopColor: col.color }]}>
            <Text style={[styles.columnTitle, { color: col.color }]}>{col.label}</Text>
            <View style={[styles.countBadge, { backgroundColor: col.color + '22' }]}>
              <Text style={[styles.countText, { color: col.color }]}>
                {columns[col.status].length}
              </Text>
            </View>
          </View>

          {/* Cards */}
          <ScrollView showsVerticalScrollIndicator={false}>
            {columns[col.status].length === 0 ? (
              <Text style={styles.emptyColumn}>No tasks</Text>
            ) : (
              columns[col.status].map((task) => renderCard(task, col.status))
            )}
          </ScrollView>
        </View>
      ))}
    </ScrollView>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const COLUMN_WIDTH = 260;

const styles = StyleSheet.create({
  board: { flex: 1, backgroundColor: '#F2F2F7' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },

  column: {
    width: COLUMN_WIDTH,
    marginHorizontal: 8,
    marginTop: 12,
  },
  columnHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderTopWidth: 3,
    paddingTop: 10,
    paddingHorizontal: 4,
    marginBottom: 10,
  },
  columnTitle: { fontSize: 14, fontWeight: '700' },
  countBadge: {
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  countText: { fontSize: 12, fontWeight: '700' },

  card: {
    backgroundColor: '#fff',
    borderRadius: 10,
    padding: 12,
    marginBottom: 10,
    shadowColor: '#000',
    shadowOpacity: 0.06,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  cardOverdue: {
    borderLeftWidth: 3,
    borderLeftColor: '#FF3B30',
  },
  cardTitle: { fontSize: 14, fontWeight: '500', color: '#1C1C1E', marginBottom: 6 },
  cardDue: { fontSize: 12, color: '#8E8E93' },
  cardDueOverdue: { color: '#FF3B30' },
  cardAssignee: { fontSize: 11, color: '#007AFF', marginTop: 4 },
  cardCommentCount: { fontSize: 11, color: '#8E8E93', marginTop: 2 },

  moveRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  moveChip: {
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 8,
    paddingVertical: 3,
  },
  moveChipText: { fontSize: 11, fontWeight: '500' },

  emptyColumn: {
    textAlign: 'center',
    color: '#C6C6C8',
    fontSize: 13,
    marginTop: 20,
  },
});
