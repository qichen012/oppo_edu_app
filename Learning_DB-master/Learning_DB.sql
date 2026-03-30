-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema Learning_DB
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema Learning_DB
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `Learning_DB` ;
USE `Learning_DB` ;

-- -----------------------------------------------------
-- Table `Learning_DB`.`user_information`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`user_information` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `name` VARCHAR(45) NULL,
  `email` VARCHAR(45) NULL UNIQUE,
  `password` VARCHAR(255) NULL,
  `gender` ENUM('male', 'female') NULL,
  `age` INT NULL,
  `current_subject` VARCHAR(100) NULL,
  PRIMARY KEY (`id`),
  INDEX `idx_email` (`email` ASC) VISIBLE)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`source_documents`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`source_documents` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `file_name` VARCHAR(100) NULL,
  `file_path` VARCHAR(100) NULL,
  `upload_date` DATE NOT NULL,
  `processed_status` ENUM('Pending', 'Done', 'Failed') NOT NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  CONSTRAINT `fk_sourcedocuments_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`daily_briefs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`daily_briefs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `posterior_insight` VARCHAR(100) NULL,
  `key_concepts` TEXT NULL,
  `created_at` DATETIME NULL,
  `review_stage` INT NULL,
  `User_reflect` TEXT NULL,
  `source_handouts` VARCHAR(100) NULL,
  `origin` ENUM('SC','PDF') NULL,
  `prompt_question` TEXT NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  INDEX `idx_dailybriefs_created_at` (`created_at` ASC) VISIBLE,
  CONSTRAINT `fk_dailybriefs_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`elite_idea_cards`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`elite_idea_cards` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `daily_brief_id` INT NULL,
  `origin_concept` VARCHAR(100) NULL,
  `meta_idea_name` VARCHAR(100) NULL,
  `meta_explanation` VARCHAR(100) NULL,
  `create_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  INDEX `id_idx` (`daily_brief_id` ASC) VISIBLE,
  CONSTRAINT `fk_eliteideacards_dailybriefs`
    FOREIGN KEY (`daily_brief_id`)
    REFERENCES `Learning_DB`.`daily_briefs` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`elite_idea_cases`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`elite_idea_cases` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `meta_id` INT NULL,
  `case_title` VARCHAR(100) NULL,
  `case_content` VARCHAR(100) NULL,
  `image_path` VARCHAR(100) NULL,
  `query_rewrite` TEXT NULL,
  PRIMARY KEY (`id`),
  INDEX `id_idx` (`meta_id` ASC) VISIBLE,
  CONSTRAINT `fk_eliteideacases_eliteideacards`
    FOREIGN KEY (`meta_id`)
    REFERENCES `Learning_DB`.`elite_idea_cards` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`external_resources`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`external_resources` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `card_id` INT NULL,
  `title` VARCHAR(100) NULL,
  `url` VARCHAR(100) NULL,
  `LLM_context` TEXT NULL,
  `source` VARCHAR(100) NULL,
  PRIMARY KEY (`id`),
  INDEX `id_idx` (`card_id` ASC) VISIBLE,
  CONSTRAINT `fk_externalresources_eliteideacards`
    FOREIGN KEY (`card_id`)
    REFERENCES `Learning_DB`.`elite_idea_cards` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`user_screenshots`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`user_screenshots` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `image_path` VARCHAR(100) NULL,
  `vlm_analysis` TEXT NULL,
  `upload_date` DATE NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  INDEX `idx_userscreenshots_upload_date` (`upload_date` ASC) VISIBLE,
  CONSTRAINT `fk_userscreenshots_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`association_briefs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`association_briefs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `content` TEXT NULL,
  `notes_date` DATETIME NULL,
  `screenshot_date` DATE NULL,
  `created_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  INDEX `idx_associationbriefs_notes_date` (`notes_date` ASC) VISIBLE,
  INDEX `idx_associationbriefs_screenshot_date` (`screenshot_date` ASC) VISIBLE,
  CONSTRAINT `fk_associationbriefs_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_associationbriefs_dailybriefs`
    FOREIGN KEY (`notes_date`)
    REFERENCES `Learning_DB`.`daily_briefs` (`created_at`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_associationbriefs_userscreenshots`
    FOREIGN KEY (`screenshot_date`)
    REFERENCES `Learning_DB`.`user_screenshots` (`upload_date`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`knowledge_maps`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`knowledge_maps` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `source_doc_id` INT NULL,
  `map_json` JSON NULL,
  `created_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  INDEX `source_documents.id_idx` (`source_doc_id` ASC) VISIBLE,
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  CONSTRAINT `fk_knowledgemaps_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_knowledgemaps_sourcedocuments`
    FOREIGN KEY (`source_doc_id`)
    REFERENCES `Learning_DB`.`source_documents` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`map_interaction_logs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`map_interaction_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `source_doc_id` INT NULL,
  `node_id` VARCHAR(100) NULL,
  `user_query` TEXT NULL,
  `ai_response` TEXT NULL,
  `created_at` DATETIME NULL,
  `is_distilled` INT NULL,
  PRIMARY KEY (`id`),
  INDEX `source_documents.id_idx` (`source_doc_id` ASC) VISIBLE,
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  CONSTRAINT `fk_mapinteractionlogs_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_mapinteraction_sourcedocuments`
    FOREIGN KEY (`source_doc_id`)
    REFERENCES `Learning_DB`.`source_documents` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`map_cognitive_snapshots`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`map_cognitive_snapshots` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `source_doc_id` INT NULL,
  `last_processed_log_id` INT NULL,
  `snapshot_content` TEXT NULL,
  `path_nodes` JSON NULL,
  `version` INT NULL,
  `last_log_id` INT NULL,
  PRIMARY KEY (`id`),
  INDEX `source_documents.id_idx` (`source_doc_id` ASC) VISIBLE,
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  CONSTRAINT `fk_mapcognitivesnapshots_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_mapcognitivesnapshots_sourcedocuments`
    FOREIGN KEY (`source_doc_id`)
    REFERENCES `Learning_DB`.`source_documents` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`scholar_notes`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`scholar_notes` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `daily_brief_id` INT NULL,
  `note_title` VARCHAR(100) NULL,
  `note_content` TEXT NULL,
  `created_at` DATETIME NULL,
  `updated_at` DATETIME NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  INDEX `daily_briefs.id_idx` (`daily_brief_id` ASC) VISIBLE,
  CONSTRAINT `fk_scholarnotes_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_scholarnotes_dailybriefs`
    FOREIGN KEY (`daily_brief_id`)
    REFERENCES `Learning_DB`.`daily_briefs` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;


-- -----------------------------------------------------
-- Table `Learning_DB`.`app_usage_logs`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `Learning_DB`.`app_usage_logs` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `user_id` INT NULL,
  `start_time` DATETIME NULL,
  `end_time` DATETIME NULL,
  `duration_seconds` INT NULL,
  PRIMARY KEY (`id`),
  INDEX `users.id_idx` (`user_id` ASC) VISIBLE,
  CONSTRAINT `fk_appusagelogs_userinformation`
    FOREIGN KEY (`user_id`)
    REFERENCES `Learning_DB`.`user_information` (`id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;