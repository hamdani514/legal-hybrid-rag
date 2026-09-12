/**
 * Copy for the three policy pages linked from the footer.
 *
 * This is plain-language product policy written for the Verdict AI research
 * tool — it describes how the platform behaves. It is not legal advice, and
 * it should be reviewed by counsel before the product goes to production.
 */

export const LEGAL_DOCUMENTS = {
  privacy: {
    slug: 'privacy',
    eyebrow: 'Policy',
    title: 'Privacy Policy',
    banner: 'Privacy|Policy',
    summary:
      'What Verdict AI collects when you research, how long it is kept, and the guarantees that apply to your queries.',
    updated: 'Last reviewed: 26 August 2026',
    sections: [
      {
        id: 'what-we-collect',
        heading: 'What we collect',
        body: [
          'Account details you provide at sign-up: name, username, email address, organisation, phone number, date of birth, and your selected plan.',
          'Operational records needed to run the service: session timestamps, the queries you submit, and the documents returned to you.',
          'Support correspondence you send through the contact form, so we can answer it and keep a record of the thread.',
        ],
      },
      {
        id: 'how-we-use-it',
        heading: 'How we use it',
        body: [
          'To authenticate you, run retrieval against the judgment archive, and return results attributed to their source document and page.',
          'To maintain your private research history so that earlier sessions remain available to you.',
          'To investigate faults, prevent abuse, and meet our legal obligations.',
        ],
      },
      {
        id: 'what-we-never-do',
        heading: 'What we never do',
        body: [
          'We do not train retrieval or language models on your queries, your uploads, or your research paths.',
          'We do not sell, rent, or disclose your data to advertisers or data brokers.',
          'We do not read the contents of your workspace except where you explicitly ask support to look at a specific session.',
        ],
      },
      {
        id: 'security',
        heading: 'Security',
        body: [
          'Data is encrypted with AES-256 in transit and at rest. Access to production systems is restricted, logged, and reviewed.',
          'Each account operates in an isolated workspace; one account cannot reach another account’s sessions, drafts, or saved research.',
        ],
      },
      {
        id: 'retention',
        heading: 'Retention and deletion',
        body: [
          'Research sessions are retained for as long as your account is active, because they form your private knowledge base.',
          'You may request deletion of your account and its associated research at any time by writing to BSE231005@cust.pk. We action deletion requests within 30 days.',
        ],
      },
      {
        id: 'contact-privacy',
        heading: 'Questions',
        body: [
          'Privacy questions and data requests go to BSE231005@cust.pk, or through the contact form on this site.',
        ],
      },
    ],
  },

  terms: {
    slug: 'terms',
    eyebrow: 'Agreement',
    title: 'Terms of Service',
    banner: 'Terms of|Service',
    summary:
      'The terms you accept when you create a Verdict AI account and use the research console.',
    updated: 'Last reviewed: 26 August 2026',
    sections: [
      {
        id: 'accounts',
        heading: 'Accounts',
        body: [
          'You must provide accurate registration details and keep your credentials confidential. You are responsible for activity carried out under your account.',
          'Accounts are for individual use. Firm-wide and chambers-wide access is available as a separate licence — contact us to arrange one rather than sharing a single login.',
        ],
      },
      {
        id: 'acceptable-use',
        heading: 'Acceptable use',
        body: [
          'Use the service for legitimate legal research. Do not attempt to scrape the archive wholesale, reverse-engineer the retrieval index, or resell access.',
          'Do not upload material you are not entitled to process, and do not use the service to build a competing index of the judgments we host.',
        ],
      },
      {
        id: 'plans',
        heading: 'Plans and billing',
        body: [
          'A free account includes 10 research sessions per month. The Individual tier is $10/month for 50 sessions; the Professional tier is $20/month for unlimited research.',
          'Plans renew monthly and can be changed or cancelled at any time. Cancellation takes effect at the end of the current billing period.',
        ],
      },
      {
        id: 'availability',
        heading: 'Availability',
        body: [
          'We aim for continuous availability but do not guarantee uninterrupted service. Maintenance windows and index rebuilds may briefly affect retrieval.',
        ],
      },
      {
        id: 'liability',
        heading: 'Limitation of liability',
        body: [
          'Verdict AI is a research aid. To the fullest extent permitted by law, we are not liable for decisions taken, filings made, or outcomes reached on the basis of material surfaced through the service.',
          'Read the Legal Disclaimer for the full statement on how results should be treated.',
        ],
      },
      {
        id: 'changes',
        heading: 'Changes to these terms',
        body: [
          'We may update these terms as the product changes. Material changes will be announced in the console before they take effect.',
        ],
      },
    ],
  },

  disclaimer: {
    slug: 'disclaimer',
    eyebrow: 'Important',
    title: 'Legal Disclaimer',
    banner: 'Legal|Disclaimer',
    summary:
      'Verdict AI assists legal research. It does not give legal advice, and it does not replace reading the judgment.',
    updated: 'Last reviewed: 26 August 2026',
    sections: [
      {
        id: 'not-advice',
        heading: 'Not legal advice',
        body: [
          'Nothing produced by Verdict AI constitutes legal advice, and no advocate–client relationship is created by using the service.',
          'Summaries, rankings, and extracted passages are research output. Professional judgement remains yours.',
        ],
      },
      {
        id: 'verify',
        heading: 'Verify before you cite',
        body: [
          'Every result links back to its source document and page precisely so you can check it. Read the original judgment before relying on a passage in a brief, an opinion, or in court.',
          'Retrieval systems can rank a passage highly and still be wrong about its relevance to your matter. Treat a result as a lead, not as a holding.',
        ],
      },
      {
        id: 'currency',
        heading: 'Currency of the archive',
        body: [
          'The index is rebuilt several times a day, but a judgment can be reported, corrected, or overruled between rebuilds. Confirm that an authority is still good law before you rely on it.',
        ],
      },
      {
        id: 'jurisdiction',
        heading: 'Scope',
        body: [
          'The current archive covers reported judgments of the Supreme Court of Pakistan. Results should not be assumed to reflect the law of any other jurisdiction.',
        ],
      },
      {
        id: 'contact-disclaimer',
        heading: 'Raise a correction',
        body: [
          'If you find an indexing error or a misattributed citation, tell us at BSE231005@cust.pk and we will investigate it.',
        ],
      },
    ],
  },
};

export const LEGAL_SLUGS = Object.keys(LEGAL_DOCUMENTS);
