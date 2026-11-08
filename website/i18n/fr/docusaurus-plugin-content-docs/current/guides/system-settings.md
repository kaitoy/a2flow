---
title: Paramètres système
sidebar_position: 13
---

# Paramètres système

Les Paramètres système permettent de configurer le serveur de messagerie par lequel passent les [e-mails de notification](./notifications.md#email-delivery), ainsi que le HashiCorp Vault global. Il existe un seul enregistrement de paramètres pour tout le déploiement, initialisé au premier démarrage avec l'envoi d'e-mails **désactivé** : sur une nouvelle installation, les notifications restent donc dans l'application jusqu'à ce qu'un opérateur active l'envoi.

Ouvrez **Paramètres système** dans la barre latérale d'administration. Comme les [Tenants](./users-and-groups.md#tenants), cette section est réservée au **Super administrateur** : les paramètres s'appliquent à toute la plateforme et non à un tenant, si bien qu'aucune exception n'est prévue pour les administrateurs de tenant, et même leur lecture est refusée à quiconque d'autre.

## Les paramètres {#the-settings}

| Champ | Rôle |
|---|---|
| **URL de base de l'application** | Destination des liens des e-mails de notification, par exemple `https://a2flow.example.com`. Si ce champ reste vide, les messages sont envoyés sans lien. |
| **Envoyer les notifications par e-mail** | L'interrupteur général. Tant qu'il est désactivé, les notifications restent dans l'application et rien n'est envoyé. |
| **Hôte SMTP** / **Port SMTP** | Le relais auquel remettre les messages. |
| **Sécurité** | **STARTTLS** (par défaut), **SSL/TLS** (TLS implicite) ou **Aucun**. |
| **Nom d'utilisateur SMTP** / **Mot de passe SMTP** | Identifiants SMTP AUTH. Laissez le nom d'utilisateur vide pour un relais qui n'en exige pas. |
| **Adresse de l'expéditeur** / **Nom de l'expéditeur** | L'adresse d'envoi et le nom d'affichage facultatif qui l'accompagne. |

L'activation de l'envoi sans hôte ni adresse d'expéditeur est refusée : le formulaire ne peut donc pas être enregistré dans un état qui échouerait silencieusement plus tard.

Chaque champ peut également être défini depuis l'environnement, ce qui permet à un déploiement de livrer sa configuration de messagerie au lieu d'en faire une étape manuelle — voir [E-mail de notification](../operations/configuration.md#notification-email). Ces variables sont réappliquées à chaque démarrage : une valeur définie ainsi écrase donc ce qui a été saisi ici.

Le mot de passe est en **écriture seule**, comme les [secrets](./secrets.md) et les mots de passe des utilisateurs : il n'est jamais réaffiché. Une fois un mot de passe stocké, le champ apparaît vide avec l'indication « Enregistré — laissez vide pour le conserver », et enregistrer en le laissant vide conserve le mot de passe stocké au lieu de l'effacer.

## Le Vault global {#global-vault}

Le Vault global est le HashiCorp Vault (KV v2 uniquement) dans lequel tout tenant **sans Vault propre** lit ses [secrets de type Vault](./secrets.md). L'administrateur d'un tenant peut connecter à la place le Vault propre du tenant dans les [Paramètres du tenant](./users-and-groups.md#tenant-vault), et celui-ci a toujours la priorité.

| Champ | Rôle |
|---|---|
| **Adresse du Vault global** | L'adresse du Vault, commençant par `http://` ou `https://`. Contrairement au Vault propre d'un tenant, il peut se trouver sur un réseau privé. Laissez ce champ vide et enregistrez pour déconnecter le Vault global. |

Seule l'adresse se définit ici. Il n'y a pas d'identifiant partagé : chaque tenant se connecte avec **un identifiant qui lui est propre**, qu'un super administrateur enregistre sur la page du tenant (voir [L'identifiant du Vault global](./users-and-groups.md#global-vault-credential)). Un tenant sans identifiant ne peut pas du tout lire le Vault global.

Les tenants sont cloisonnés **par Vault lui-même** : un secret est lu au **Point de montage Vault** et au **Chemin Vault** qu'il indique, et les stratégies associées à l'identifiant du tenant décident si cette lecture est autorisée. Délivrez à chaque tenant un identifiant dont la stratégie ne couvre que les données de ce tenant — par exemple un AppRole par tenant, avec une stratégie comme celle-ci pour le tenant `acme` :

```hcl
path "secret/data/tenants/acme/*" {
  capabilities = ["read"]
}
```

## Vérifier la configuration {#checking-the-configuration}

**Envoyer un e-mail de test** remet un message de test fixe en utilisant les paramètres *enregistrés* : une erreur de configuration apparaît ainsi immédiatement, et non la prochaine fois qu'un workflow déclenche une notification.

1. Enregistrez d'abord les paramètres : le test utilise ce qui est stocké, pas ce qui est à l'écran.
2. Cliquez sur **Envoyer un e-mail de test**.
3. Consultez votre propre boîte de réception. Le destinataire est forcément l'adresse du super administrateur connecté et ne peut pas être changé.

Un échec du relais s'affiche sous forme d'erreur sur la page ; la cause sous-jacente est consignée dans les journaux du serveur.
