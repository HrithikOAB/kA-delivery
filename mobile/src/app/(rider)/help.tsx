import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useRef, useState } from 'react';
import {
  Alert,
  Linking,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { api, ApiError } from '@/api/client';
import type { SupportHelp } from '@/api/types';
import { ErrorState } from '@/components/ErrorState';
import { FeedbackBanner } from '@/components/FeedbackBanner';
import { useFeedback } from '@/components/FeedbackProvider';
import { Loading } from '@/components/Loading';
import { PartnerCard } from '@/components/partner';
import { Button } from '@/components/ui/Button';
import { IconButton } from '@/components/ui/IconButton';
import { PressableScale } from '@/components/ui/PressableScale';
import { Text } from '@/components/ui/Text';
import { colors, radius, shadow, spacing } from '@/theme';

const MESSAGE_LIMIT = 500;

function categoryIcon(icon: string): keyof typeof Ionicons.glyphMap {
  if (icon === 'wallet') return 'wallet';
  if (icon === 'delivery') return 'bicycle';
  if (icon === 'person') return 'person';
  if (icon === 'shield') return 'shield';
  return 'help-circle';
}

function ticketStatusStyle(status: string) {
  if (status === 'in_review') {
    return { bg: colors.warningSoft, text: colors.warning };
  }
  if (status === 'open') {
    return { bg: colors.infoSoft, text: colors.info };
  }
  if (status === 'resolved' || status === 'closed') {
    return { bg: colors.secondarySoft, text: colors.secondary };
  }
  return { bg: colors.surfaceContainerHigh, text: colors.textMuted };
}

export default function HelpSupport() {
  const router = useRouter();
  const feedback = useFeedback();
  const scrollRef = useRef<ScrollView>(null);
  const ticketsY = useRef(0);

  const [data, setData] = useState<SupportHelp | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [category, setCategory] = useState('');
  const [topic, setTopic] = useState('');
  const [message, setMessage] = useState('');
  const [attachment, setAttachment] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [openFaqId, setOpenFaqId] = useState<number | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const help = await api.supportHelp();
      setData(help);
      setError(null);
      setCategory((prev) => {
        const next = (prev && help.categories.some((c) => c.key === prev))
          ? prev
          : help.categories[0]?.key ?? '';
        const cat = help.categories.find((c) => c.key === next);
        setTopic((prevTopic) => {
          if (prevTopic && cat?.topics.some((t) => t.key === prevTopic)) return prevTopic;
          return cat?.topics[0]?.key ?? '';
        });
        return next;
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load help & support');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const selectedCategory = data?.categories.find((c) => c.key === category) ?? data?.categories[0];
  const topics = selectedCategory?.topics ?? [];
  const selectedTopic = topics.find((t) => t.key === topic) ?? topics[0];

  const selectCategory = (key: string) => {
    setCategory(key);
    const cat = data?.categories.find((c) => c.key === key);
    setTopic(cat?.topics[0]?.key ?? '');
  };

  const pickTopic = () => {
    if (!topics.length) return;
    Alert.alert(
      'Related Topic',
      'Choose the topic that best matches your issue.',
      [
        ...topics.map((t) => ({
          text: t.label,
          onPress: () => setTopic(t.key),
        })),
        { text: 'Cancel', style: 'cancel' },
      ],
    );
  };

  const pickAttachment = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (perm.status !== 'granted') {
      feedback.warning('Allow photo access to attach a screenshot.', 'Permission needed');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.7,
    });
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    setAttachment({
      uri: asset.uri,
      name: asset.fileName ?? 'attachment.jpg',
      type: asset.mimeType ?? 'image/jpeg',
    });
  };

  const submit = async () => {
    if (!message.trim() || !category || !topic) return;
    setSubmitting(true);
    setError(null);
    try {
      await api.submitSupportTicket({
        category,
        topic,
        message: message.trim(),
        file: attachment ?? undefined,
      });
      setSubmitted(true);
      setMessage('');
      setAttachment(null);
      feedback.success('Your support request has been submitted.', 'Submitted');
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not submit request');
    } finally {
      setSubmitting(false);
    }
  };

  const scrollToTickets = () => {
    scrollRef.current?.scrollTo({ y: ticketsY.current, animated: true });
  };

  if (loading && !data) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={styles.header}>
          <IconButton icon="arrow-back" onPress={() => router.back()} color={colors.text} />
          <Text variant="h3">Help & Support</Text>
          <View style={styles.headerSpacer} />
        </View>
        <Loading label="Loading help & support…" />
      </SafeAreaView>
    );
  }

  if (!data && error) {
    return (
      <SafeAreaView style={styles.screen} edges={['top']}>
        <View style={styles.header}>
          <IconButton icon="arrow-back" onPress={() => router.back()} color={colors.text} />
          <Text variant="h3">Help & Support</Text>
          <View style={styles.headerSpacer} />
        </View>
        <ErrorState message={error} onRetry={load} variant="page" />
      </SafeAreaView>
    );
  }

  if (!data) return null;

  const waitLabel = data.agent_desk.avg_wait_minutes < 2
    ? '< 2 mins'
    : `< ${data.agent_desk.avg_wait_minutes} mins`;

  return (
    <SafeAreaView style={styles.screen} edges={['top']}>
      <View style={styles.header}>
        <IconButton icon="arrow-back" onPress={() => router.back()} color={colors.text} />
        <Text variant="h3">Help & Support</Text>
        <View style={styles.headerActions}>
          <IconButton
            icon="chatbubble-ellipses"
            onPress={() => feedback.info('Live chat with Agent Desk is opening.', 'Agent Desk')}
          />
          <IconButton icon="document-text" onPress={scrollToTickets} />
        </View>
      </View>

      <ScrollView
        ref={scrollRef}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {error ? <ErrorState message={error} variant="inline" onRetry={load} /> : null}
        {submitted ? (
          <FeedbackBanner
            severity="success"
            title="Request submitted"
            message="Our support team will review your request shortly."
            style={{ marginBottom: spacing.sm }}
          />
        ) : null}

        <PartnerCard style={styles.sosCard}>
          <View style={styles.sosRow}>
            <View style={styles.sosIcon}>
              <Ionicons name="warning" size={22} color={colors.danger} />
            </View>
            <View style={styles.sosBody}>
              <Text variant="label">In an active delivery emergency?</Text>
              <Text variant="bodySmall" style={styles.sosSubtext}>
                Accidents, safety threats, or navigation breakdown during an active delivery — call our SOS hotline immediately.
              </Text>
            </View>
          </View>
          <Button
            title="Call Rider SOS Hotline"
            onPress={() => Linking.openURL(`tel:${data.sos_hotline}`)}
            style={{ marginTop: spacing.md }}
          />
        </PartnerCard>

        <PartnerCard style={styles.agentCard}>
          <View style={styles.agentRow}>
            <View style={styles.agentAvatarWrap}>
              <View style={styles.agentAvatar}>
                <Ionicons name="headset" size={20} color={colors.primary} />
              </View>
              {data.agent_desk.is_live ? <View style={styles.liveDot} /> : null}
            </View>
            <View style={styles.agentInfo}>
              <View style={styles.agentTitleRow}>
                <Text variant="label">Agent Desk</Text>
                {data.agent_desk.is_live ? (
                  <View style={styles.liveBadge}>
                    <Text variant="caption" style={styles.liveBadgeText}>Live</Text>
                  </View>
                ) : null}
              </View>
              <Text variant="caption" style={{ color: colors.textMuted }}>
                Avg. wait time: {waitLabel}
              </Text>
            </View>
            <PressableScale
              onPress={() => feedback.info('Connecting you to a live agent…', 'Agent Desk')}
              style={styles.chatBtn}
            >
              <Text variant="caption" style={styles.chatBtnText}>Chat</Text>
            </PressableScale>
          </View>
        </PartnerCard>

        <Text variant="label" style={styles.sectionLabel}>Select Support Category</Text>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.chips}
        >
          {data.categories.map((c) => {
            const active = category === c.key;
            return (
              <Pressable
                key={c.key}
                onPress={() => selectCategory(c.key)}
                style={[styles.chip, active && styles.chipActive]}
              >
                <Ionicons
                  name={categoryIcon(c.icon)}
                  size={15}
                  color={active ? colors.onPrimary : colors.text}
                />
                <Text
                  variant="caption"
                  style={[styles.chipText, active && styles.chipTextActive]}
                >
                  {c.label}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>

        <PartnerCard style={styles.formCard}>
          <View style={styles.formHeader}>
            <View style={styles.formTitleRow}>
              <View style={styles.formIcon}>
                <Ionicons name="help-circle" size={18} color={colors.primary} />
              </View>
              <Text variant="label">Submit Dispute or Query</Text>
            </View>
            <View style={styles.priorityBadge}>
              <Text variant="caption" style={styles.priorityText}>Priority Queue</Text>
            </View>
          </View>

          <Text variant="caption" style={styles.fieldLabel}>Related Topic</Text>
          <Pressable onPress={pickTopic} style={styles.dropdown}>
            <Text variant="bodySmall" style={{ flex: 1, color: colors.text }}>
              {selectedTopic?.label ?? 'Select a topic'}
            </Text>
            <Ionicons name="chevron-down" size={18} color={colors.textMuted} />
          </Pressable>

          <Text variant="caption" style={styles.fieldLabel}>Describe your issue</Text>
          <TextInput
            style={styles.textarea}
            multiline
            numberOfLines={5}
            placeholder="Provide details so our team can help faster…"
            placeholderTextColor={colors.outline}
            value={message}
            onChangeText={(t) => setMessage(t.slice(0, MESSAGE_LIMIT))}
            maxLength={MESSAGE_LIMIT}
          />
          <Text variant="caption" style={styles.charCount}>
            {message.length} / {MESSAGE_LIMIT}
          </Text>

          <Pressable onPress={() => { void pickAttachment(); }} style={styles.attachBtn}>
            <Ionicons name="attach" size={18} color={colors.primary} />
            <Text variant="caption" style={styles.attachText}>
              {attachment ? attachment.name : 'Add Attachment / Screenshot (Optional)'}
            </Text>
          </Pressable>

          <PressableScale
            onPress={() => { void submit(); }}
            disabled={!message.trim() || submitting}
            style={[styles.submitBtn, (!message.trim() || submitting) && styles.submitBtnDisabled]}
          >
            {submitting ? (
              <Text variant="button" style={styles.submitBtnText}>Submitting…</Text>
            ) : (
              <View style={styles.submitRow}>
                <Text variant="button" style={styles.submitBtnText}>Submit Request</Text>
                <Ionicons name="arrow-forward" size={18} color={colors.onPrimary} />
              </View>
            )}
          </PressableScale>
        </PartnerCard>

        <View
          style={styles.sectionHeader}
          onLayout={(e) => { ticketsY.current = e.nativeEvent.layout.y; }}
        >
          <Text variant="h3">Ongoing Tickets</Text>
          <View style={styles.countBadge}>
            <Text variant="caption" style={styles.countBadgeText}>
              {data.active_ticket_count} Active
            </Text>
          </View>
        </View>

        {data.ongoing_tickets.length === 0 ? (
          <PartnerCard style={styles.emptyTicket}>
            <Text variant="bodySmall" style={{ color: colors.textMuted }}>
              No active tickets. Submit a request above if you need help.
            </Text>
          </PartnerCard>
        ) : (
          data.ongoing_tickets.map((ticket) => {
            const statusStyle = ticketStatusStyle(ticket.status);
            return (
              <PartnerCard key={ticket.id} style={styles.ticketCard}>
                <View style={styles.ticketTop}>
                  <Text variant="caption" style={styles.ticketNumber}>{ticket.ticket_number}</Text>
                  <View style={[styles.statusBadge, { backgroundColor: statusStyle.bg }]}>
                    <Text variant="caption" style={{ color: statusStyle.text, fontWeight: '700' }}>
                      {ticket.status_label}
                    </Text>
                  </View>
                </View>
                <Text variant="label" style={{ marginTop: spacing.xs }}>{ticket.title}</Text>
                <Text variant="caption" style={{ color: colors.textMuted, marginTop: spacing.xs }}>
                  {ticket.subtitle}
                </Text>
              </PartnerCard>
            );
          })
        )}

        <View style={styles.sectionHeader}>
          <Text variant="h3">Frequently Asked Questions</Text>
          <View style={styles.guidesBadge}>
            <Text variant="caption" style={styles.guidesText}>{data.faqs.length} guides</Text>
          </View>
        </View>

        {data.faqs.map((faq) => {
          const open = openFaqId === faq.id;
          return (
            <PartnerCard key={faq.id} style={styles.faqCard}>
              <Pressable onPress={() => setOpenFaqId(open ? null : faq.id)}>
                <View style={styles.faqHeader}>
                  <Text variant="label" style={{ flex: 1 }}>{faq.question}</Text>
                  <Ionicons
                    name={open ? 'chevron-up' : 'chevron-down'}
                    size={18}
                    color={colors.textMuted}
                  />
                </View>
              </Pressable>
              {open ? (
                <Text variant="bodySmall" style={styles.faqAnswer}>{faq.answer}</Text>
              ) : null}
            </PartnerCard>
          );
        })}

        <View style={styles.footer}>
          <View style={styles.footerIcon}>
            <Ionicons name="headset" size={22} color={colors.textMuted} />
          </View>
          <Text variant="label" style={styles.footerTitle}>
            Khana Delivery Partner Desk is available 24/7 via chat and phone.
          </Text>
          <Text variant="caption" style={styles.footerSubtext}>
            Our rider protection team monitors safety reports and payout disputes around the clock.
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
  },
  headerSpacer: { width: 88 },
  headerActions: { flexDirection: 'row', gap: spacing.xs },
  content: { padding: spacing.lg, paddingBottom: spacing.massive },
  sosCard: { backgroundColor: colors.dangerSoft, marginBottom: spacing.md },
  sosRow: { flexDirection: 'row', gap: spacing.md },
  sosIcon: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sosBody: { flex: 1, gap: spacing.xs },
  sosSubtext: { color: colors.textMuted },
  agentCard: { marginBottom: spacing.lg },
  agentRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  agentAvatarWrap: { position: 'relative' },
  agentAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  liveDot: {
    position: 'absolute',
    right: 0,
    bottom: 0,
    width: 12,
    height: 12,
    borderRadius: 6,
    backgroundColor: colors.secondary,
    borderWidth: 2,
    borderColor: colors.surface,
  },
  agentInfo: { flex: 1, gap: 2 },
  agentTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  liveBadge: {
    backgroundColor: colors.secondarySoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  liveBadgeText: { color: colors.secondary, fontWeight: '700' },
  chatBtn: {
    backgroundColor: colors.surfaceContainerHigh,
    borderRadius: radius.button,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  chatBtnText: { color: colors.text, fontWeight: '600' },
  sectionLabel: { color: colors.textMuted, marginBottom: spacing.sm },
  chips: { gap: spacing.sm, marginBottom: spacing.lg },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceContainerHigh,
  },
  chipActive: { backgroundColor: colors.primary },
  chipText: { color: colors.text, fontWeight: '600' },
  chipTextActive: { color: colors.onPrimary },
  formCard: { marginBottom: spacing.lg },
  formHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  formTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1 },
  formIcon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: colors.primarySoft,
    alignItems: 'center',
    justifyContent: 'center',
  },
  priorityBadge: {
    backgroundColor: colors.accentSoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  priorityText: { color: colors.accentDark, fontWeight: '700' },
  fieldLabel: { color: colors.textMuted, marginBottom: spacing.xs, marginTop: spacing.sm },
  dropdown: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  textarea: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    minHeight: 110,
    textAlignVertical: 'top',
    color: colors.text,
  },
  charCount: { color: colors.textMuted, textAlign: 'right', marginTop: spacing.xs },
  attachBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.md,
    marginBottom: spacing.md,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderStyle: 'dashed',
    backgroundColor: colors.surface,
  },
  attachText: { color: colors.primary, fontWeight: '600' },
  submitBtn: {
    backgroundColor: colors.primary,
    borderRadius: radius.button,
    paddingVertical: spacing.md + 2,
    paddingHorizontal: spacing.xl,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
    ...shadow,
  },
  submitBtnDisabled: { opacity: 0.5 },
  submitRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  submitBtnText: { color: colors.onPrimary },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
    marginTop: spacing.md,
  },
  countBadge: {
    backgroundColor: colors.primarySoft,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
  },
  countBadgeText: { color: colors.primary, fontWeight: '700' },
  guidesBadge: {
    backgroundColor: colors.surfaceContainerHigh,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
  },
  guidesText: { color: colors.textMuted, fontWeight: '600' },
  emptyTicket: { marginBottom: spacing.sm },
  ticketCard: { marginBottom: spacing.sm },
  ticketTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  ticketNumber: { color: colors.textMuted, fontWeight: '600' },
  statusBadge: {
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  faqCard: { marginBottom: spacing.sm, padding: spacing.md },
  faqHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  faqAnswer: { color: colors.textMuted, marginTop: spacing.sm },
  footer: {
    marginTop: spacing.xl,
    backgroundColor: colors.surfaceContainerHigh,
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
    gap: spacing.sm,
  },
  footerIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  footerTitle: { textAlign: 'center' },
  footerSubtext: { color: colors.textMuted, textAlign: 'center' },
});
