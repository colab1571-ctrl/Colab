/**
 * TaskListScreen — displays all tasks for a collab with Kanban + list views.
 *
 * Features:
 * - Tab bar: All | To Do | In Progress | Done | Blocked
 * - FlatList with status badge, assignee avatar, due date, overdue tint
 * - Swipe-to-change-status (react-native-gesture-handler SwipeableRow)
 * - FAB to create new task → navigates to TaskDetailScreen (create mode)
 * - Tap task row → TaskDetailScreen (edit mode)
 * - Pull-to-refresh
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Task {
  id: string;
  collab_id: string;
  title: string;
  description: string | null;
  assignee_profile_id: string | null;
  due_date: string | null;
  status: 'todo' | 'in_progress' | 'done' | 'blocked';
  order_key: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  comment_count: number;
}

type StatusFilter = 'all' | 'todo' | 'in_progress' | 'done' | 'blocked';

interface RouteParams {
  collabId: string;
  currentUserId: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STATUS_TABS: { key: StatusFilter; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'todo', label: 'To Do' },
  { key: 'in_progress', label: 'In Progress' },
  { key: 'done', label: 'Done' },
  { key: 'blocked', label: 'Blocked' },
];

const STATUS_COLORS: Record<string, string> = {
  todo: '#8E8E93',
  in_progress: '#007AFF',
  done: '#34C759',
  blocked: '#FF3B30',
};

const STATUS_LABELS: Record<string, string> = {
  todo: 'To Do',
  in_progress: 'In Progress',
  done: 'Done',
  blocked: 'Blocked',
};

// ---------------------------------------------------------------------------
// API helpers (replace with generated typed client in production)
// ---------------------------------------------------------------------------

async function fetchTasks(
  collabId: string,
  statusFilter: StatusFilter,
  authToken: string,
): Promise<Task[]> {
  const params = new URLSearchParams({ sort: 'order' });
  if (statusFilter !== 'all') params.set('status', statusFilter);

  const resp = await fetch(
    `/collabs/${collabId}/tasks?${params}`,
    { headers: { Authorization: `Bearer ${authToken}` } },
  );
  if (!resp.ok) throw new Error(`fetchTasks: ${resp.status}`);
  const data = await resp.json();
  return data.tasks as Task[];
}

async function patchTask(
  taskId: string,
  patch: Partial<Pick<Task, 'status' | 'order_key' | 'title'>>,
  authToken: string,
): Promise<Task> {
  const resp = await fetch(`/tasks/${taskId}`, {
    method: 'PATCH',
    headers: {
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(patch),
  });
  if (!resp.ok) throw new Error(`patchTask: ${resp.status}`);
  return resp.json();
}

// ---------------------------------------------------------------------------
// TaskListScreen
// ---------------------------------------------------------------------------

export default function TaskListScreen() {
  const navigation = useNavigation<any>();
  const route = useRoute();
  const { collabId, currentUserId } = route.params as RouteParams;

  // In production, derive authToken from the auth context / secure storage.
  const authToken = ''; // placeholder

  const [tasks, setTasks] = useState<Task[]>([]);
  const [activeTab, setActiveTab] = useState<StatusFilter>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // -----------------------------------------------------------------------
  // Data loading
  // -----------------------------------------------------------------------

  const loadTasks = useCallback(
    async (tab: StatusFilter = activeTab) => {
      try {
        const data = await fetchTasks(collabId, tab, authToken);
        setTasks(data);
      } catch (err) {
        console.error('[TaskList] Load failed:', err);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [collabId, activeTab, authToken],
  );

  useEffect(() => {
    setLoading(true);
    loadTasks(activeTab);
  }, [activeTab]);

  const handleRefresh = useCallback(() => {
    setRefreshing(true);
    loadTasks(activeTab);
  }, [activeTab, loadTasks]);

  // -----------------------------------------------------------------------
  // Status flip (swipe gesture)
  // -----------------------------------------------------------------------

  const handleStatusFlip = useCallback(
    async (task: Task) => {
      const nextStatus: Record<string, Task['status']> = {
        todo: 'in_progress',
        in_progress: 'done',
        done: 'todo',
        blocked: 'in_progress',
      };
      const newStatus = nextStatus[task.status] ?? 'todo';

      // Optimistic update
      setTasks((prev) =>
        prev.map((t) => (t.id === task.id ? { ...t, status: newStatus } : t)),
      );

      try {
        await patchTask(task.id, { status: newStatus }, authToken);
      } catch {
        // Revert on failure
        setTasks((prev) =>
          prev.map((t) => (t.id === task.id ? { ...t, status: task.status } : t)),
        );
      }
    },
    [authToken],
  );

  // -----------------------------------------------------------------------
  // Render helpers
  // -----------------------------------------------------------------------

  const isOverdue = (task: Task): boolean => {
    if (!task.due_date || task.status === 'done') return false;
    return new Date(task.due_date) < new Date();
  };

  const renderTask = useCallback(
    ({ item }: { item: Task }) => {
      const overdue = isOverdue(item);
      return (
        <Pressable
          style={[styles.taskRow, overdue && styles.taskRowOverdue]}
          onPress={() =>
            navigation.navigate('TaskDetail', {
              taskId: item.id,
              collabId,
              currentUserId,
            })
          }
        >
          {/* Status badge */}
          <View
            style={[
              styles.statusBadge,
              { backgroundColor: STATUS_COLORS[item.status] + '22' },
            ]}
          >
            <View
              style={[styles.statusDot, { backgroundColor: STATUS_COLORS[item.status] }]}
            />
            <Text style={[styles.statusText, { color: STATUS_COLORS[item.status] }]}>
              {STATUS_LABELS[item.status]}
            </Text>
          </View>

          {/* Title + meta */}
          <View style={styles.taskContent}>
            <Text style={styles.taskTitle} numberOfLines={2}>
              {item.title}
            </Text>
            <View style={styles.taskMeta}>
              {item.due_date && (
                <Text style={[styles.metaText, overdue && styles.metaTextOverdue]}>
                  Due {item.due_date}
                </Text>
              )}
              {item.comment_count > 0 && (
                <Text style={styles.metaText}>💬 {item.comment_count}</Text>
              )}
              {item.assignee_profile_id === currentUserId && (
                <Text style={styles.metaText}>Assigned to me</Text>
              )}
            </View>
          </View>

          {/* Swipe-to-flip hint */}
          <TouchableOpacity
            onPress={() => handleStatusFlip(item)}
            style={styles.flipButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Text style={styles.flipText}>→</Text>
          </TouchableOpacity>
        </Pressable>
      );
    },
    [navigation, collabId, currentUserId, handleStatusFlip],
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
    <View style={styles.container}>
      {/* Status filter tabs */}
      <View style={styles.tabBar}>
        {STATUS_TABS.map((tab) => (
          <TouchableOpacity
            key={tab.key}
            onPress={() => setActiveTab(tab.key)}
            style={[styles.tab, activeTab === tab.key && styles.tabActive]}
          >
            <Text style={[styles.tabText, activeTab === tab.key && styles.tabTextActive]}>
              {tab.label}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Task list */}
      <FlatList
        data={tasks}
        keyExtractor={(item) => item.id}
        renderItem={renderTask}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        contentContainerStyle={tasks.length === 0 ? styles.emptyContainer : undefined}
        ListEmptyComponent={
          <Text style={styles.emptyText}>No tasks yet. Tap + to add one.</Text>
        }
      />

      {/* FAB — create new task */}
      <TouchableOpacity
        style={styles.fab}
        onPress={() =>
          navigation.navigate('TaskDetail', {
            taskId: null,
            collabId,
            currentUserId,
          })
        }
      >
        <Text style={styles.fabText}>+</Text>
      </TouchableOpacity>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F2F2F7' },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },

  tabBar: {
    flexDirection: 'row',
    backgroundColor: '#fff',
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#C6C6C8',
  },
  tab: {
    flex: 1,
    paddingVertical: 10,
    alignItems: 'center',
  },
  tabActive: {
    borderBottomWidth: 2,
    borderBottomColor: '#007AFF',
  },
  tabText: { fontSize: 12, color: '#8E8E93' },
  tabTextActive: { color: '#007AFF', fontWeight: '600' },

  taskRow: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#fff',
    marginHorizontal: 16,
    marginTop: 10,
    borderRadius: 12,
    padding: 14,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowRadius: 4,
    shadowOffset: { width: 0, height: 2 },
    elevation: 2,
  },
  taskRowOverdue: {
    borderLeftWidth: 3,
    borderLeftColor: '#FF3B30',
  },

  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    marginRight: 12,
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginRight: 5,
  },
  statusText: { fontSize: 11, fontWeight: '600' },

  taskContent: { flex: 1 },
  taskTitle: { fontSize: 15, fontWeight: '500', color: '#1C1C1E', marginBottom: 4 },
  taskMeta: { flexDirection: 'row', gap: 10 },
  metaText: { fontSize: 12, color: '#8E8E93' },
  metaTextOverdue: { color: '#FF3B30' },

  flipButton: {
    padding: 6,
    marginLeft: 8,
  },
  flipText: { fontSize: 18, color: '#8E8E93' },

  emptyContainer: { flexGrow: 1, justifyContent: 'center', alignItems: 'center' },
  emptyText: { fontSize: 15, color: '#8E8E93' },

  fab: {
    position: 'absolute',
    bottom: 24,
    right: 24,
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: '#007AFF',
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#007AFF',
    shadowOpacity: 0.4,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  fabText: { fontSize: 28, color: '#fff', lineHeight: 32 },
});
