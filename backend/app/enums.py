from enum import StrEnum


class JobStatus(StrEnum):
    queued = "queued"
    discovering = "discovering"
    researching = "researching"
    analyzing = "analyzing"
    generating_report = "generating_report"
    completed = "completed"
    partial = "partial"
    failed = "failed"
    cancelled = "cancelled"


ACTIVE_STATUSES = frozenset(
    {
        JobStatus.queued,
        JobStatus.discovering,
        JobStatus.researching,
        JobStatus.analyzing,
        JobStatus.generating_report,
    }
)
RUNNING_STATUSES = ACTIVE_STATUSES - {JobStatus.queued}
TERMINAL_STATUSES = frozenset(
    {JobStatus.completed, JobStatus.partial, JobStatus.failed, JobStatus.cancelled}
)


class SourceType(StrEnum):
    website = "website"
    social = "social"


class Platform(StrEnum):
    website = "website"
    linkedin = "linkedin"
    instagram = "instagram"
    youtube = "youtube"
    facebook = "facebook"
    x = "x"


SOCIAL_PLATFORMS = [Platform.linkedin, Platform.instagram, Platform.youtube, Platform.facebook, Platform.x]
ALL_PLATFORMS = [Platform.website, *SOCIAL_PLATFORMS]


class VerificationStatus(StrEnum):
    verified = "verified"
    unverified = "unverified"
    rejected = "rejected"


class AccessStatus(StrEnum):
    completed = "completed"
    partial = "partial"
    inaccessible = "inaccessible"
    not_discovered = "not_discovered"
    unsupported = "unsupported"
    failed = "failed"


class FindingClass(StrEnum):
    observed_fact = "observed_fact"
    inference = "inference"
    unknown = "unknown"


class Confidence(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class ReviewStatus(StrEnum):
    unreviewed = "unreviewed"
    accepted = "accepted"
    rejected = "rejected"
